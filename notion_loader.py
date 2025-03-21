import streamlit as st
import requests
import pandas as pd
from barcode import EAN13
from barcode.writer import ImageWriter
from PIL import Image
import io
import time
from requests.exceptions import RequestException

# Add imports for Notion API
import json

# ---------- Functions to fetch book data ----------

def fetch_from_google_books(isbn):
    url = f'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}'
    for attempt in range(3):  # Retry up to 3 times
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'items' in data:
                    volume_info = data['items'][0]['volumeInfo']
                    title = volume_info.get('title')
                    authors = ', '.join(volume_info.get('authors', []))
                    cover_url = volume_info.get('imageLinks', {}).get('thumbnail')
                    categories = ', '.join(volume_info.get('categories', []))
                    page_count = volume_info.get('pageCount')
                    return {
                        'Title': title,
                        'Authors': authors,
                        'Cover URL': cover_url,
                        'Categories': categories,
                        'Page Count': page_count
                    }
            break  # Exit loop if successful
        except RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)  # Wait before retrying
    return {'Title': None, 'Authors': None, 'Cover URL': None, 'Categories': None, 'Page Count': None}

def fetch_from_open_library(isbn):
    url = f'https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data'
    for attempt in range(3):  # Retry up to 3 times
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                key = f'ISBN:{isbn}'
                if key in data:
                    book_data = data[key]
                    title = book_data.get('title')
                    # Authors: list of dicts with "name" keys or list of strings.
                    authors_list = book_data.get('authors', [])
                    if authors_list and isinstance(authors_list[0], dict):
                        authors = ', '.join(author.get('name', '') for author in authors_list)
                    else:
                        authors = ', '.join(authors_list)
                    cover_url = book_data.get('cover', {}).get('medium')
                    
                    # Subjects might be a list of dicts or strings.
                    subjects = book_data.get('subjects', [])
                    if subjects and isinstance(subjects[0], dict):
                        subjects = ', '.join(item.get('name', '') for item in subjects)
                    else:
                        subjects = ', '.join(subjects)
                    
                    page_count = book_data.get('number_of_pages')
                    return {
                        'Title': title,
                        'Authors': authors,
                        'Cover URL': cover_url,
                        'Categories': subjects,  # Using 'subjects' as categories.
                        'Page Count': page_count
                    }
            break  # Exit loop if successful
        except RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)  # Wait before retrying
    return {'Title': None, 'Authors': None, 'Cover URL': None, 'Categories': None, 'Page Count': None}

def merge_book_data(isbn, google_data, open_library_data):
    # For each field, use Google Books data if available; otherwise fallback to Open Library.
    return {
        'ISBN': isbn,
        'Title': google_data['Title'] or open_library_data['Title'] or 'N/A',
        'Authors': google_data['Authors'] or open_library_data['Authors'] or 'N/A',
        'Cover URL': google_data['Cover URL'] or open_library_data['Cover URL'] or 'N/A',
        'Categories/Subjects': google_data['Categories'] or open_library_data['Categories'] or 'N/A',
        'Page Count': google_data['Page Count'] or open_library_data['Page Count'] or 'N/A'
    }

# ---------- New Functions for Multi-ISBN Processing and Notion Integration ----------

def read_isbns_from_file(file_path):
    """Reads a text file containing one ISBN per line."""
    with open(file_path, 'r') as file:
        isbns = list(set([line.strip() for line in file if line.strip()]))
    return isbns

def fetch_books_data(isbns):
    """Fetches book data for a list of ISBNs and returns a pandas DataFrame."""
    books_data = []
    for isbn in isbns:
        google_data = fetch_from_google_books(isbn)
        open_library_data = fetch_from_open_library(isbn)
        merged_data = merge_book_data(isbn, google_data, open_library_data)
        books_data.append(merged_data)
    return pd.DataFrame(books_data)

def create_notion_page(notion_token, database_id, book_data):
    """Creates a new page in a Notion database for the given book data."""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    # Construct the payload for the Notion API
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Title": {
                "title": [{"text": {"content": book_data['Title']}}]
            },
            "Authors": {
                "rich_text": [{"text": {"content": book_data['Authors']}}]
            },
            "Categories/Subjects": {
                "multi_select": [{"name": category.strip()} for category in book_data['Categories/Subjects'].split(',')]
            },
            "Page Count": {
                "number": book_data['Page Count'] if isinstance(book_data['Page Count'], int) else None
            },
            "ISBN": {
                "rich_text": [{"text": {"content": book_data['ISBN']}}]
            },
            "Status": {
                "status": {"name": "To be read"}
            }
        }
    }
    # Add cover image if available
    if book_data['Cover URL'] and book_data['Cover URL'] != 'N/A':
        payload["cover"] = {
            "external": {"url": book_data['Cover URL']}
        }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.status_code, response.json()

def process_isbns_and_update_notion(file_path, notion_token, database_id):
    """Reads ISBNs from a file, fetches their data, and updates a Notion database."""
    isbns = read_isbns_from_file(file_path)
    books_df = fetch_books_data(isbns)
    for _, book_data in books_df.iterrows():
        status_code, response = create_notion_page(notion_token, database_id, book_data)
        if status_code != 200:
            print(f"Failed to create page for ISBN {book_data['ISBN']}: {response}")
        else:
            print(f"Successfully created page for ISBN {book_data['ISBN']}")
    return books_df

# ---------- Example Usage ----------
# Read the Notion token from a file
with open('notion-token.txt', 'r') as token_file:
    notion_token = token_file.read().strip()
with open('notion-id.txt', 'r') as id_file:
    notion_id = id_file.read().strip()

# file_path = "path_to_your_isbn_file.txt"
process_isbns_and_update_notion(file_path='book-summary.txt', notion_token=notion_token, database_id=notion_id)
