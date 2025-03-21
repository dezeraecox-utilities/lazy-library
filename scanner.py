import streamlit as st
import requests
import pandas as pd
from barcode import EAN13
from barcode.writer import ImageWriter
from PIL import Image
import io

# ---------- Functions to fetch book data ----------

def fetch_from_google_books(isbn):
    url = f'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}'
    response = requests.get(url)
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
    return {'Title': None, 'Authors': None, 'Cover URL': None, 'Categories': None, 'Page Count': None}

def fetch_from_open_library(isbn):
    url = f'https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data'
    response = requests.get(url)
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

# ---------- Function to decode barcode from an image ----------

def decode_barcode(image_data):
    """
    Given a BytesIO image_data from st.camera_input, decode the barcode (ISBN)
    using python-barcode and return the decoded string.
    """
    try:
        image = Image.open(image_data)
        # Convert the image to grayscale for better processing
        image = image.convert("L")
        # Extract barcode data using python-barcode (EAN13 format assumed)
        barcode = EAN13(image, writer=ImageWriter())
        return barcode.get_fullcode()
    except Exception as e:
        st.error(f"Error decoding barcode: {e}")
    return None

# ---------- Streamlit App ----------

st.title("The Lazy Library: Barcode Scanner")

# Initialize session state for ISBN list if not already present.
if 'isbn_list' not in st.session_state:
    st.session_state.isbn_list = []

st.header("Phase 1: Scan Barcodes")

# Provide a camera input for scanning barcodes.
image_file = st.camera_input("Scan a Barcode")
if image_file is not None:
    scanned_isbn = decode_barcode(image_file)
    if scanned_isbn:
        if scanned_isbn not in st.session_state.isbn_list:
            st.session_state.isbn_list.append(scanned_isbn)
            st.success(f"Scanned ISBN: {scanned_isbn}")
        else:
            st.info("This ISBN is already in your list.")
    else:
        st.error("No barcode detected. Please try again.")

# Optional: Allow manual ISBN entry.
manual_isbn = st.text_input("Or enter ISBN manually:")
if st.button("Add Manual ISBN"):
    if manual_isbn:
        if manual_isbn not in st.session_state.isbn_list:
            st.session_state.isbn_list.append(manual_isbn)
            st.success(f"Added ISBN: {manual_isbn}")
        else:
            st.info("This ISBN is already in your list.")
    else:
        st.error("Please enter a valid ISBN.")

st.write("**Current ISBN List:**", st.session_state.isbn_list)

st.header("Phase 2: Retrieve Book Data & Download")

if st.button("Next"):
    if not st.session_state.isbn_list:
        st.error("No ISBNs found. Please scan or add at least one ISBN.")
    else:
        book_data_list = []
        for isbn in st.session_state.isbn_list:
            google_data = fetch_from_google_books(isbn)
            open_library_data = fetch_from_open_library(isbn)
            book_info = merge_book_data(isbn, google_data, open_library_data)
            book_data_list.append(book_info)
        
        if book_data_list:
            df = pd.DataFrame(book_data_list)
            st.write("### Book Data Retrieved", df)
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="book_data.csv",
                mime="text/csv"
            )
