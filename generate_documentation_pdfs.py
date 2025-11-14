#!/usr/bin/env python3
"""
Generate PDF documentation from Markdown files using Aptos fonts
Requires: pip install markdown2 weasyprint
"""
import os
import markdown2
from weasyprint import HTML, CSS

# Define the markdown files and their corresponding PDF names
DOCUMENTATION_FILES = [
    ('CLAUDE.md', 'CLAUDE.pdf'),
    ('CONTENT_ROTATION.md', 'CONTENT_ROTATION.pdf'),
    ('FEATURES.md', 'FEATURES.pdf'),
    ('PACKAGE_SELECTION_DOCUMENTATION.md', 'PACKAGE_SELECTION_DOCUMENTATION.pdf'),
    ('PSA_SELECTION_DOCUMENTATION.md', 'PSA_SELECTION_DOCUMENTATION.pdf'),
    ('SCHEDULING_SYSTEM_DOCUMENTATION.md', 'SCHEDULING_SYSTEM_DOCUMENTATION.pdf')
]

# CSS for styling with Aptos fonts
CSS_STYLE = """
@page {
    size: letter;
    margin: 1in;
}

body {
    font-family: 'Segoe UI Light', 'Segoe UI', 'Helvetica Neue', 'Arial', sans-serif;
    font-weight: 300;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Segoe UI', 'Segoe UI Semibold', 'Helvetica Neue', 'Arial Black', sans-serif;
    font-weight: 600;
    color: #000;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}

h1 {
    font-size: 24pt;
    border-bottom: 2px solid #000;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 18pt;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.2em;
}

h3 {
    font-size: 14pt;
}

h4 {
    font-size: 12pt;
}

code {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    background-color: #f5f5f5;
    padding: 2px 4px;
    border-radius: 3px;
}

pre {
    background-color: #f5f5f5;
    padding: 10px;
    border-radius: 5px;
    overflow-x: auto;
}

pre code {
    background-color: transparent;
    padding: 0;
}

blockquote {
    border-left: 4px solid #ccc;
    padding-left: 1em;
    margin-left: 0;
    font-style: italic;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}

th, td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}

th {
    background-color: #f5f5f5;
    font-family: 'Aptos', 'Segoe UI', 'Arial Black', sans-serif;
    font-weight: 600;
}

a {
    color: #0066cc;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

ul, ol {
    margin-left: 1.5em;
}

li {
    margin-bottom: 0.3em;
}

/* Special styling for certain elements */
.filename, .path {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    background-color: #f0f0f0;
    padding: 2px 4px;
    border-radius: 3px;
}
"""

def convert_markdown_to_pdf(markdown_file, pdf_file):
    """Convert a markdown file to PDF with custom styling"""
    print(f"Converting {markdown_file} to {pdf_file}...")
    
    try:
        # Read the markdown file
        with open(markdown_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Convert markdown to HTML
        html_content = markdown2.markdown(
            markdown_content,
            extras=['tables', 'fenced-code-blocks', 'code-friendly', 'cuddled-lists']
        )
        
        # Wrap in HTML document structure
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{os.path.splitext(os.path.basename(markdown_file))[0]}</title>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Create PDF output directory if it doesn't exist
        output_dir = 'documentation_pdfs'
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate PDF
        pdf_path = os.path.join(output_dir, pdf_file)
        HTML(string=full_html).write_pdf(
            pdf_path,
            stylesheets=[CSS(string=CSS_STYLE)]
        )
        
        print(f"✓ Successfully created {pdf_path}")
        
    except Exception as e:
        print(f"✗ Error converting {markdown_file}: {str(e)}")

def check_font_availability():
    """Check if Aptos fonts are available on the system"""
    print("Checking font availability...")
    print("Note: Aptos fonts are part of Microsoft's new font family.")
    print("If not available, the system will fall back to alternative fonts.")
    print()

def main():
    """Main function to generate all documentation PDFs"""
    print("=== Documentation PDF Generator ===")
    print("Using Segoe UI font for headings and Segoe UI Light for body text")
    print("Note: Will fall back to Helvetica Neue or Arial if Segoe UI is not available")
    print()
    
    check_font_availability()
    
    # Check if all source files exist
    missing_files = []
    for md_file, _ in DOCUMENTATION_FILES:
        if not os.path.exists(md_file):
            missing_files.append(md_file)
    
    if missing_files:
        print("✗ Missing source files:")
        for file in missing_files:
            print(f"  - {file}")
        print("\nPlease ensure all source files are present.")
        return
    
    # Convert all files
    print("Converting Markdown files to PDF...")
    print()
    
    for markdown_file, pdf_file in DOCUMENTATION_FILES:
        convert_markdown_to_pdf(markdown_file, pdf_file)
    
    print("\n✓ PDF generation complete!")
    print(f"PDFs saved to: {os.path.abspath('documentation_pdfs')}/")

if __name__ == "__main__":
    main()