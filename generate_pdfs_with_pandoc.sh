#!/bin/bash
# Generate PDFs from Markdown using pandoc with custom fonts
# Requires: brew install pandoc

echo "=== Documentation PDF Generator using Pandoc ==="
echo "Using Segoe UI font for headings and Segoe UI Light for body text"
echo

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

# Create a custom LaTeX template for Segoe UI fonts
cat > segoe_template.tex << 'EOF'
\documentclass[11pt,letterpaper]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fontspec}
\usepackage{hyperref}
\usepackage{fancyhdr}
\usepackage{listings}
\usepackage{color}
\usepackage{longtable,booktabs}

% Use Segoe UI fonts, fall back to system fonts if not available
\IfFontExistsTF{Segoe UI Light}{
  \setmainfont{Segoe UI Light}
  \setsansfont{Segoe UI}
  \newfontfamily\headingfont[]{Segoe UI}
}{
  \IfFontExistsTF{Helvetica Neue Light}{
    \setmainfont{Helvetica Neue Light}
    \setsansfont{Helvetica Neue}
    \newfontfamily\headingfont[]{Helvetica Neue}
  }{
    \setmainfont{Arial}
    \setsansfont{Arial Black}
    \newfontfamily\headingfont[]{Arial Black}
  }
}

% Configure headings to use heading font
\usepackage{sectsty}
\allsectionsfont{\headingfont}

% Code formatting
\setmonofont{Consolas}
\lstset{
    basicstyle=\ttfamily\small,
    breaklines=true,
    frame=single,
    backgroundcolor=\color[gray]{0.95}
}

% Hyperlink setup
\hypersetup{
    colorlinks=true,
    linkcolor=black,
    filecolor=blue,
    urlcolor=blue,
}

% Header/footer
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0pt}

$if(title)$
\title{$title$}
$endif$
$if(author)$
\author{$author$}
$endif$
$if(date)$
\date{$date$}
$endif$

\begin{document}

$if(title)$
\maketitle
$endif$

$if(toc)$
\tableofcontents
\newpage
$endif$

$body$

\end{document}
EOF

echo "Converting Markdown files to PDF..."
echo

# Convert each file
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        output_file="documentation_pdfs/${file%.md}.pdf"
        echo "Converting $file to $output_file..."
        
        pandoc "$file" \
            -o "$output_file" \
            --pdf-engine=xelatex \
            --template=segoe_template.tex \
            --highlight-style=tango \
            -V geometry:margin=1in \
            -V linkcolor:blue \
            -V urlcolor:blue \
            --toc \
            2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo "✓ Successfully created $output_file"
        else
            echo "✗ Error converting $file"
            # Try without custom template as fallback
            echo "  Trying with default template..."
            pandoc "$file" \
                -o "$output_file" \
                --pdf-engine=xelatex \
                -V mainfont="Segoe UI Light" \
                -V sansfont="Segoe UI" \
                -V monofont="Consolas" \
                -V fontsize=11pt \
                -V geometry:margin=1in \
                --toc
        fi
    else
        echo "✗ File not found: $file"
    fi
    echo
done

# Clean up template
rm -f segoe_template.tex

echo "✓ PDF generation complete!"
echo "PDFs saved to: $(pwd)/documentation_pdfs/"