import pdfplumber

SAMPLE_PDF = "sample.pdf"  # Replace with your sample PDF filename if different

print(f" Opening {SAMPLE_PDF}...")

with pdfplumber.open(SAMPLE_PDF) as pdf:
    # Render page 1 at 300 DPI (high quality)
    page_img = pdf.pages[0].to_image(resolution=300).original
    
    # Save as template.png in your project folder
    page_img.save("template.png")
    
print("Saved 'template.png' as your master calibration reference.")