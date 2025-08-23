#!/usr/bin/env python3
"""
Extract text from scanned PDF files using OCR.
"""

import sys
import os
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

def extract_text_with_ocr(pdf_path):
    """Extract text from PDF using OCR."""
    try:
        print(f"\n{'='*60}")
        print(f"Processing PDF with OCR: {pdf_path}")
        print(f"{'='*60}\n")
        
        # Convert PDF to images
        print("Converting PDF to images...")
        images = convert_from_path(pdf_path, dpi=300)
        print(f"Found {len(images)} page(s)")
        
        all_text = ""
        for i, image in enumerate(images):
            print(f"\nProcessing page {i + 1}...")
            
            # Perform OCR on the image
            text = pytesseract.image_to_string(image)
            
            if text.strip():
                print(f"\n--- Page {i + 1} Text ---")
                print(text)
                print(f"--- End Page {i + 1} ---")
                all_text += f"Page {i + 1}:\n{text}\n\n"
            else:
                print(f"No text found on page {i + 1}")
        
        return all_text
        
    except Exception as e:
        print(f"Error processing PDF {pdf_path}: {str(e)}")
        print("\nNote: This error might occur if:")
        print("1. Tesseract is not installed (run: brew install tesseract)")
        print("2. poppler is not installed (run: brew install poppler)")
        import traceback
        traceback.print_exc()
        return ""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        text = extract_text_with_ocr(pdf_path)
        
        # Save to file
        output_file = pdf_path.replace('.pdf', '_ocr.txt')
        with open(output_file, 'w') as f:
            f.write(text)
        print(f"\nSaved OCR text to: {output_file}")
    else:
        # Process all three PDFs
        pdf_files = [
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-48 PM.pdf',
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-49 PM.pdf',
            '/Users/jaypound/Documents/TURBOSCAN/Doc - Aug 21 2025 - 2-50 PM.pdf'
        ]
        
        for pdf in pdf_files:
            text = extract_text_with_ocr(pdf)
            
            # Save extracted text
            output_file = pdf.replace('.pdf', '_ocr.txt')
            if text:
                with open(output_file, 'w') as f:
                    f.write(text)
                print(f"\nSaved OCR text to: {output_file}")