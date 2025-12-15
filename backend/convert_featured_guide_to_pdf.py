#!/usr/bin/env python3
"""
Convert FEATURED_CONTENT_GUIDE.md to PDF
"""
import os
import subprocess
import sys
from datetime import datetime

def convert_markdown_to_pdf():
    """Convert the Featured Content Guide markdown file to PDF"""
    
    # Define paths
    markdown_file = "FEATURED_CONTENT_GUIDE.md"
    output_dir = "../documentation_pdfs"
    output_file = os.path.join(output_dir, "FEATURED_CONTENT_GUIDE.pdf")
    
    # Check if markdown file exists
    if not os.path.exists(markdown_file):
        print(f"Error: {markdown_file} not found in current directory")
        return False
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Converting {markdown_file} to PDF...")
    
    # Try using pandoc with xelatex engine
    try:
        # Build pandoc command
        cmd = [
            "pandoc",
            markdown_file,
            "-o", output_file,
            "--pdf-engine=xelatex",
            "-V", "geometry:margin=1in",
            "-V", "fontsize=11pt",
            "-V", "linkcolor:blue",
            "-V", "urlcolor:blue",
            "--highlight-style=tango",
            "--toc",
            "--toc-depth=2"
        ]
        
        # Try to use nice fonts if available
        font_options = [
            "-V", "mainfont=Helvetica Neue Light",
            "-V", "sansfont=Helvetica Neue",
            "-V", "monofont=Menlo"
        ]
        cmd.extend(font_options)
        
        # Run pandoc
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✓ Successfully created {output_file}")
            file_size = os.path.getsize(output_file)
            print(f"  File size: {file_size:,} bytes")
            return True
        else:
            print("First attempt failed, trying with simpler options...")
            
            # Try again with simpler options
            cmd = [
                "pandoc",
                markdown_file,
                "-o", output_file,
                "--pdf-engine=pdflatex",
                "-V", "geometry:margin=1in",
                "-V", "fontsize=11pt",
                "--toc"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✓ Successfully created {output_file} with basic formatting")
                file_size = os.path.getsize(output_file)
                print(f"  File size: {file_size:,} bytes")
                return True
            else:
                print(f"✗ Error: {result.stderr}")
                return False
                
    except FileNotFoundError:
        print("Error: pandoc not found. Please install pandoc:")
        print("  On macOS: brew install pandoc")
        print("  On Ubuntu/Debian: sudo apt-get install pandoc texlive-xetex")
        print("  On Windows: Download from https://pandoc.org/installing.html")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def create_html_fallback():
    """Create an HTML version as a fallback"""
    markdown_file = "FEATURED_CONTENT_GUIDE.md"
    output_dir = "../documentation_pdfs"
    html_file = os.path.join(output_dir, "FEATURED_CONTENT_GUIDE.html")
    
    try:
        import markdown2
        
        # Read markdown content
        with open(markdown_file, 'r') as f:
            md_content = f.read()
        
        # Convert to HTML
        html_content = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks'])
        
        # Wrap in HTML document with styling
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Featured Content Scheduling Guide</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-weight: 300;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
        }}
        h1, h2, h3, h4, h5, h6 {{
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }}
        h1 {{ font-size: 2.5rem; }}
        h2 {{ font-size: 2rem; }}
        h3 {{ font-size: 1.5rem; }}
        code {{
            background-color: #f5f5f5;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: Consolas, Monaco, 'Courier New', monospace;
            font-size: 0.9em;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 1rem;
            border-radius: 5px;
            overflow-x: auto;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1rem 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f5f5f5;
            font-weight: 600;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        @media print {{
            body {{
                max-width: none;
                margin: 0;
                padding: 1in;
            }}
        }}
    </style>
</head>
<body>
    {html_content}
    <hr>
    <p style="text-align: center; color: #666; font-size: 0.9em;">
        Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </p>
</body>
</html>"""
        
        # Write HTML file
        with open(html_file, 'w') as f:
            f.write(full_html)
        
        print(f"✓ Created HTML fallback: {html_file}")
        print("  You can open this in a browser and print to PDF if needed")
        return True
        
    except ImportError:
        print("markdown2 not installed for HTML fallback")
        return False
    except Exception as e:
        print(f"Error creating HTML fallback: {e}")
        return False

def main():
    print("=== Featured Content Guide PDF Converter ===\n")
    
    # Try to convert to PDF
    success = convert_markdown_to_pdf()
    
    if not success:
        print("\nAttempting to create HTML fallback...")
        create_html_fallback()
    
    print("\n✓ Conversion process complete!")
    
    # List files in documentation_pdfs directory
    output_dir = "../documentation_pdfs"
    if os.path.exists(output_dir):
        print(f"\nFiles in {output_dir}:")
        for file in sorted(os.listdir(output_dir)):
            file_path = os.path.join(output_dir, file)
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                print(f"  - {file} ({size:,} bytes)")

if __name__ == "__main__":
    main()