#!/bin/bash

# Script to convert all Markdown documentation files to PDF format
# Requires: pandoc and a LaTeX engine (BasicTeX or MacTeX)

echo "==================================="
echo "Markdown to PDF Conversion Script"
echo "==================================="

# Check if pandoc is installed
if ! command -v pandoc &> /dev/null; then
    echo "❌ pandoc is not installed!"
    echo ""
    echo "To install pandoc on macOS:"
    echo "  brew install pandoc"
    echo ""
    echo "Or download from: https://pandoc.org/installing.html"
    exit 1
fi

# Check if pdflatex is installed (needed for PDF generation)
if ! command -v pdflatex &> /dev/null; then
    echo "❌ LaTeX is not installed!"
    echo ""
    echo "To install BasicTeX on macOS (smaller, recommended):"
    echo "  brew install --cask basictex"
    echo ""
    echo "Or install MacTeX (full distribution, 4GB+):"
    echo "  brew install --cask mactex"
    echo ""
    echo "After installing, you may need to restart your terminal."
    exit 1
fi

# Create output directory
OUTPUT_DIR="./documentation_pdfs"
mkdir -p "$OUTPUT_DIR"

echo ""
echo "📁 Output directory: $OUTPUT_DIR"
echo ""

# Counter for processed files
processed=0
failed=0

# Convert each markdown file
for md_file in *.md; do
    if [ -f "$md_file" ]; then
        # Get filename without extension
        base_name=$(basename "$md_file" .md)
        output_file="$OUTPUT_DIR/${base_name}.pdf"
        
        echo "📄 Converting: $md_file"
        
        # Convert with nice formatting
        # --toc: Table of contents
        # -V geometry: Page margins
        # --highlight-style: Syntax highlighting for code blocks
        # -V colorlinks: Colored links
        # -V linkcolor: Link color
        # -V urlcolor: URL color
        pandoc "$md_file" \
            -o "$output_file" \
            --pdf-engine=pdflatex \
            --toc \
            --toc-depth=3 \
            -V geometry:"top=1in, bottom=1in, left=1in, right=1in" \
            -V colorlinks=true \
            -V linkcolor=blue \
            -V urlcolor=blue \
            -V toccolor=black \
            --highlight-style=tango \
            -V fontsize=11pt \
            -V documentclass=article \
            --metadata title="${base_name//_/ }" \
            2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo "   ✅ Success: $output_file"
            ((processed++))
        else
            echo "   ❌ Failed: $md_file"
            ((failed++))
            
            # Try simpler conversion without TOC if first attempt failed
            echo "   🔄 Retrying with basic settings..."
            pandoc "$md_file" \
                -o "$output_file" \
                --pdf-engine=pdflatex \
                -V geometry:"margin=1in" \
                -V fontsize=11pt \
                2>/dev/null
                
            if [ $? -eq 0 ]; then
                echo "   ✅ Success with basic settings: $output_file"
                ((processed++))
                ((failed--))
            fi
        fi
        echo ""
    fi
done

# Summary
echo "==================================="
echo "Conversion Complete!"
echo "==================================="
echo "✅ Successfully converted: $processed files"
if [ $failed -gt 0 ]; then
    echo "❌ Failed conversions: $failed files"
fi
echo ""
echo "📁 PDFs saved in: $OUTPUT_DIR"
echo ""

# Open the output directory (macOS)
if [ $processed -gt 0 ]; then
    echo "Opening output directory..."
    open "$OUTPUT_DIR" 2>/dev/null || echo "Please navigate to $OUTPUT_DIR to view your PDFs"
fi