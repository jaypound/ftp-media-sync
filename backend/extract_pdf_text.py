#!/usr/bin/env python3
"""
Extract and display text from PDF files to understand their format.
"""

import sys
import PyPDF2

def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"\n{'='*60}")
            print(f"PDF: {pdf_path}")
            print(f"Number of pages: {len(pdf_reader.pages)}")
            print(f"{'='*60}\n")
            
            text = ""
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                print(f"\n--- Page {page_num + 1} ---")
                print(page_text)
                print(f"--- End Page {page_num + 1} ---\n")
                text += page_text + "\n"
            
            return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {str(e)}")
        return ""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        extract_text_from_pdf(pdf_path)
    else:
        # Process all three PDFs
        pdf_files = [
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-48 PM.pdf',
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-49 PM.pdf',
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-50 PM.pdf'
        ]
        
        for pdf in pdf_files:
            extract_text_from_pdf(pdf)