#!/usr/bin/env python3
"""
Simple PDF generation from Markdown files
This creates a notice about font requirements since we cannot directly modify PDFs
"""
import os
from datetime import datetime

def create_font_notice():
    """Create a notice about updating the PDFs with custom fonts"""
    
    notice_content = """
# Documentation PDF Font Update Instructions

The documentation PDFs need to be regenerated with the following font specifications:
- **Headings**: Aptos (regular weight)
- **Body Text**: Aptos Light

## Files to Update:
1. CLAUDE.pdf
2. CONTENT_ROTATION.pdf
3. FEATURES.pdf
4. PACKAGE_SELECTION_DOCUMENTATION.pdf
5. PSA_SELECTION_DOCUMENTATION.pdf
6. SCHEDULING_SYSTEM_DOCUMENTATION.pdf

## Recommended Methods:

### Option 1: Using Microsoft Word
1. Open each Markdown file in VS Code
2. Copy the content to Microsoft Word
3. Apply styles:
   - Headings: Aptos, Bold
   - Body text: Aptos Light
4. Export as PDF to `documentation_pdfs/` folder

### Option 2: Using Pandoc (if Aptos fonts are installed)
Run the provided shell script:
```bash
chmod +x generate_pdfs_with_pandoc.sh
./generate_pdfs_with_pandoc.sh
```

### Option 3: Using Online Converters
1. Use a Markdown to PDF converter that supports custom fonts
2. Upload the .md files
3. Specify Aptos/Aptos Light fonts
4. Download the PDFs to `documentation_pdfs/`

## Font Availability:
- Aptos is Microsoft's new default font (replacing Calibri)
- Available in Microsoft Office 2024 and Windows 11
- If Aptos is not available, use these alternatives:
  - Headings: Segoe UI (Bold)
  - Body: Segoe UI Light
  
## Note:
Direct PDF editing with custom fonts requires the fonts to be embedded in the PDF,
which requires the fonts to be available on the system generating the PDFs.

Generated on: {timestamp}
"""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notice_content = notice_content.format(timestamp=timestamp)
    
    # Save the notice
    with open('PDF_FONT_UPDATE_INSTRUCTIONS.md', 'w') as f:
        f.write(notice_content)
    
    print("Created PDF_FONT_UPDATE_INSTRUCTIONS.md")
    
    # Also create a requirements file for the Python approach
    requirements = """markdown2==2.4.10
weasyprint==60.1
pandoc==2.3
fpdf2==2.7.5
reportlab==4.0.4
"""
    
    with open('pdf_generation_requirements.txt', 'w') as f:
        f.write(requirements)
    
    print("Created pdf_generation_requirements.txt")

def check_existing_pdfs():
    """Check which PDFs exist"""
    pdf_dir = 'documentation_pdfs'
    expected_pdfs = [
        'CLAUDE.pdf',
        'CONTENT_ROTATION.pdf',
        'FEATURES.pdf',
        'PACKAGE_SELECTION_DOCUMENTATION.pdf',
        'PSA_SELECTION_DOCUMENTATION.pdf',
        'SCHEDULING_SYSTEM_DOCUMENTATION.pdf'
    ]
    
    print("\n=== Existing PDF Status ===")
    for pdf in expected_pdfs:
        pdf_path = os.path.join(pdf_dir, pdf)
        if os.path.exists(pdf_path):
            size = os.path.getsize(pdf_path)
            print(f"✓ {pdf} ({size:,} bytes)")
        else:
            print(f"✗ {pdf} (not found)")

def main():
    print("=== Documentation PDF Font Update Tool ===")
    print("\nNote: Direct PDF editing with custom fonts requires special tools.")
    print("Creating instructions for updating the PDFs with Aptos fonts...\n")
    
    create_font_notice()
    check_existing_pdfs()
    
    print("\n✓ Instructions created successfully!")
    print("\nTo update the PDFs with Aptos fonts:")
    print("1. Read PDF_FONT_UPDATE_INSTRUCTIONS.md")
    print("2. Choose one of the recommended methods")
    print("3. Regenerate all PDFs with the new fonts")
    
    print("\nNote: The Aptos font family must be installed on your system.")
    print("It's included with Microsoft Office 2024 and Windows 11.")

if __name__ == "__main__":
    main()