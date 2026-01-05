#!/usr/bin/env python3
"""
Simple HTML to PDF converter using print dialog
Since we don't have wkhtmltopdf or other converters installed,
this script opens the HTML in the default browser for manual PDF saving.
"""

import os
import subprocess
import sys

def convert_html_to_pdf():
    html_file = "return_to_automation_video_selection.html"
    
    # Check if HTML file exists
    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found!")
        return
    
    # Get absolute path
    abs_path = os.path.abspath(html_file)
    
    print(f"Opening {html_file} in your default browser...")
    print("Please use Print -> Save as PDF to create the PDF file")
    print(f"Suggested filename: return_to_automation_video_selection.pdf")
    
    # Open in default browser
    if sys.platform == "darwin":  # macOS
        subprocess.run(["open", abs_path])
    elif sys.platform == "win32":  # Windows
        os.startfile(abs_path)
    else:  # Linux and others
        subprocess.run(["xdg-open", abs_path])

if __name__ == "__main__":
    convert_html_to_pdf()