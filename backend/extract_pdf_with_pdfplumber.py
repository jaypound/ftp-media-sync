#!/usr/bin/env python3
"""
Extract text from PDF files using pdfplumber to understand their format.
"""

import sys
import pdfplumber

def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file using pdfplumber."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"\n{'='*60}")
            print(f"PDF: {pdf_path}")
            print(f"Number of pages: {len(pdf.pages)}")
            print(f"{'='*60}\n")
            
            all_text = ""
            for i, page in enumerate(pdf.pages):
                print(f"\n--- Page {i + 1} ---")
                
                # Extract text
                text = page.extract_text()
                if text:
                    print(text)
                    all_text += text + "\n"
                else:
                    print("(No text found on this page)")
                
                # Also try to extract tables if present
                tables = page.extract_tables()
                if tables:
                    print(f"\nFound {len(tables)} table(s) on page {i + 1}:")
                    for j, table in enumerate(tables):
                        print(f"\nTable {j + 1}:")
                        for row in table:
                            print("  |  ".join(str(cell) if cell else "" for cell in row))
                
                print(f"--- End Page {i + 1} ---\n")
            
            return all_text
            
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {str(e)}")
        import traceback
        traceback.print_exc()
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
            text = extract_text_from_pdf(pdf)
            
            # Save extracted text to a file for easier review
            output_file = pdf.replace('.pdf', '_extracted.txt')
            with open(output_file, 'w') as f:
                f.write(text)
            print(f"\nSaved extracted text to: {output_file}")