#!/bin/bash

# Convert markdown files with Unicode/emoji cleanup

echo "Converting files with Unicode cleanup..."

# Function to clean Unicode characters
clean_and_convert() {
    local input_file="$1"
    local output_file="$2"
    local temp_file="${input_file}.tmp"
    
    # Remove or replace problematic Unicode characters
    # This sed command removes common emojis and replaces them with text
    sed -E 's/✅/[DONE]/g; s/❌/[X]/g; s/📄/[FILE]/g; s/📁/[FOLDER]/g; s/🔄/[REFRESH]/g; s/📤/[UPLOAD]/g; s/📊/[CHART]/g; s/🤖/[BOT]/g' "$input_file" > "$temp_file"
    
    # Convert the cleaned file
    pandoc "$temp_file" \
        -o "$output_file" \
        --pdf-engine=xelatex \
        -V geometry:"margin=1in" \
        -V fontsize=11pt \
        -V mainfont="Helvetica" \
        --metadata title="${input_file%.*}" \
        2>/dev/null
    
    local result=$?
    rm -f "$temp_file"
    return $result
}

# Create output directory
mkdir -p documentation_pdfs

# Convert the failed files
for file in CLAUDE.md CONTENT_ROTATION.md; do
    if [ -f "$file" ]; then
        echo "Converting $file..."
        output="documentation_pdfs/${file%.*}.pdf"
        
        if clean_and_convert "$file" "$output"; then
            echo "✅ Success: $output"
        else
            # Try with pdflatex as fallback
            echo "Trying with pdflatex..."
            sed -E 's/✅/[DONE]/g; s/❌/[X]/g; s/📄/[FILE]/g; s/📁/[FOLDER]/g; s/🔄/[REFRESH]/g; s/📤/[UPLOAD]/g; s/📊/[CHART]/g; s/🤖/[BOT]/g; s/🛠️/[TOOL]/g; s/⚠️/[WARNING]/g' "$file" > "${file}.tmp"
            
            pandoc "${file}.tmp" \
                -o "$output" \
                --pdf-engine=pdflatex \
                -V geometry:"margin=1in" \
                -V fontsize=10pt \
                2>/dev/null
                
            if [ $? -eq 0 ]; then
                echo "✅ Success with pdflatex: $output"
            else
                echo "❌ Failed: $file"
            fi
            rm -f "${file}.tmp"
        fi
    fi
done

echo ""
echo "All conversions complete!"
echo "PDFs are in: documentation_pdfs/"