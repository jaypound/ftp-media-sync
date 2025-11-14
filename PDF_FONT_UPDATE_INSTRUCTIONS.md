
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

Generated on: 2025-11-14 12:06:44
