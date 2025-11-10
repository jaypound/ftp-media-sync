#!/usr/bin/env python3

"""
Simple Markdown to PDF converter using markdown and weasyprint
This is easier to install than pandoc + LaTeX
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required packages are installed"""
    required = ['markdown', 'weasyprint']
    missing = []
    
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing required packages:")
        print(f"   pip install {' '.join(missing)}")
        print("\nOr install all at once:")
        print("   pip install markdown weasyprint")
        return False
    return True

def convert_md_to_html_to_pdf(md_file, output_dir):
    """Convert markdown to PDF via HTML"""
    import markdown
    import weasyprint
    
    # Read markdown file
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert to HTML with extensions
    html = markdown.markdown(
        md_content,
        extensions=['extra', 'codehilite', 'toc', 'tables', 'fenced_code']
    )
    
    # Add CSS styling for better formatting
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{Path(md_file).stem.replace('_', ' ')}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 900px;
                margin: 0 auto;
                padding: 40px 20px;
            }}
            h1, h2, h3, h4, h5, h6 {{
                margin-top: 24px;
                margin-bottom: 16px;
                font-weight: 600;
                line-height: 1.25;
            }}
            h1 {{
                font-size: 2em;
                border-bottom: 1px solid #eee;
                padding-bottom: 0.3em;
            }}
            h2 {{
                font-size: 1.5em;
                border-bottom: 1px solid #eee;
                padding-bottom: 0.3em;
            }}
            h3 {{
                font-size: 1.25em;
            }}
            code {{
                background-color: #f6f8fa;
                padding: 0.2em 0.4em;
                border-radius: 3px;
                font-family: Consolas, Monaco, 'Courier New', monospace;
                font-size: 85%;
            }}
            pre {{
                background-color: #f6f8fa;
                padding: 16px;
                overflow: auto;
                border-radius: 6px;
                line-height: 1.45;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
            }}
            blockquote {{
                padding: 0 1em;
                color: #666;
                border-left: 0.25em solid #dfe2e5;
                margin: 0 0 16px 0;
            }}
            ul, ol {{
                padding-left: 2em;
                margin-bottom: 16px;
            }}
            li {{
                margin-bottom: 4px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin-bottom: 16px;
            }}
            table th, table td {{
                padding: 6px 13px;
                border: 1px solid #dfe2e5;
            }}
            table tr:nth-child(2n) {{
                background-color: #f6f8fa;
            }}
            a {{
                color: #0366d6;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            strong {{
                font-weight: 600;
            }}
            hr {{
                border: none;
                border-top: 1px solid #eee;
                margin: 24px 0;
            }}
            @page {{
                size: A4;
                margin: 20mm;
            }}
        </style>
    </head>
    <body>
        {html}
    </body>
    </html>
    """
    
    # Generate PDF
    output_file = output_dir / f"{Path(md_file).stem}.pdf"
    weasyprint.HTML(string=styled_html, base_url='.').write_pdf(output_file)
    
    return output_file

def main():
    print("===================================")
    print("Markdown to PDF Converter (Simple)")
    print("===================================")
    print()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create output directory
    output_dir = Path("documentation_pdfs")
    output_dir.mkdir(exist_ok=True)
    
    print(f"📁 Output directory: {output_dir}")
    print()
    
    # Find all markdown files
    md_files = list(Path('.').glob('*.md'))
    
    if not md_files:
        print("❌ No markdown files found in current directory!")
        sys.exit(1)
    
    # Convert each file
    processed = 0
    failed = 0
    
    for md_file in md_files:
        print(f"📄 Converting: {md_file}")
        try:
            output_file = convert_md_to_html_to_pdf(md_file, output_dir)
            print(f"   ✅ Success: {output_file}")
            processed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            failed += 1
        print()
    
    # Summary
    print("===================================")
    print("Conversion Complete!")
    print("===================================")
    print(f"✅ Successfully converted: {processed} files")
    if failed > 0:
        print(f"❌ Failed conversions: {failed} files")
    print()
    print(f"📁 PDFs saved in: {output_dir}")
    
    # Open directory on macOS
    if processed > 0 and sys.platform == 'darwin':
        subprocess.run(['open', output_dir])

if __name__ == "__main__":
    main()