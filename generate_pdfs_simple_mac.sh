#!/bin/bash
# Simple PDF generation avoiding code blocks issue
# Uses basic pandoc without syntax highlighting

echo "=== Simple Documentation PDF Generator for Mac ==="
echo "Using Helvetica Neue fonts (built into macOS)"
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

# Convert each file without syntax highlighting to avoid LaTeX package issues
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        output_file="documentation_pdfs/${file%.md}.pdf"
        echo "Converting $file to $output_file..."
        
        # Simple conversion without code highlighting
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
            --no-highlight \
            2>&1
        
        if [ $? -eq 0 ]; then
            # Get file size
            size=$(ls -lh "$output_file" | awk '{print $5}')
            echo "✓ Successfully created $output_file ($size)"
        else
            echo "✗ Error converting $file"
        fi
    else
        echo "✗ File not found: $file"
    fi
    echo
done

echo "✓ PDF generation complete!"
echo
echo "PDFs created with:"
echo "- Body text: Helvetica Neue Light (11pt)"
echo "- Headings: Helvetica Neue"
echo "- Code: Monaco"
echo
echo "Location: $(pwd)/documentation_pdfs/"

# Show all generated PDFs
echo
echo "Generated PDFs:"
ls -lh documentation_pdfs/*.pdf 2>/dev/null | awk '{print " ", $9, "("$5")"}'