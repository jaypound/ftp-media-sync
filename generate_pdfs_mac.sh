#!/bin/bash
# Generate PDFs from Markdown using pandoc with Mac system fonts
# Uses Helvetica Neue which is built into macOS

echo "=== Documentation PDF Generator for Mac ==="
echo "Using Helvetica Neue for headings and Helvetica Neue Light for body text"
echo "(These fonts are built into macOS)"
echo

# Check if pandoc is installed
if ! command -v pandoc &> /dev/null; then
    echo "Error: pandoc is not installed"
    echo "Install it with: brew install pandoc"
    exit 1
fi

# Create output directory
mkdir -p documentation_pdfs

# Define files to convert
declare -a files=(
    "CLAUDE.md"
    "CONTENT_ROTATION.md"
    "FEATURES.md"
    "PACKAGE_SELECTION_DOCUMENTATION.md"
    "PSA_SELECTION_DOCUMENTATION.md"
    "SCHEDULING_SYSTEM_DOCUMENTATION.md"
)

echo "Converting Markdown files to PDF..."
echo

# Convert each file using Helvetica Neue fonts
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        output_file="documentation_pdfs/${file%.md}.pdf"
        echo "Converting $file to $output_file..."
        
        # Use pandoc with Helvetica Neue fonts
        pandoc "$file" \
            -o "$output_file" \
            --pdf-engine=xelatex \
            -V mainfont="Helvetica Neue Light" \
            -V sansfont="Helvetica Neue" \
            -V monofont="Monaco" \
            -V fontsize=11pt \
            -V geometry:margin=1in \
            -V linkcolor:blue \
            -V urlcolor:blue \
            --highlight-style=tango \
            --toc \
            -V toc-title="Table of Contents" \
            2>&1
        
        if [ $? -eq 0 ]; then
            echo "✓ Successfully created $output_file"
        else
            echo "✗ Error converting $file"
        fi
    else
        echo "✗ File not found: $file"
    fi
    echo
done

echo "✓ PDF generation complete!"
echo "PDFs saved to: $(pwd)/documentation_pdfs/"
echo
echo "Font information:"
echo "- Body text: Helvetica Neue Light (11pt)"
echo "- Headings: Helvetica Neue (Bold)"
echo "- Code: Monaco"