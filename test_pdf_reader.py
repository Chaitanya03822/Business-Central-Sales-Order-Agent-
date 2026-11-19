
from pathlib import Path
from pdf_reader import extract_pdf_text

pdf_path = Path(r"C:\AI-BC-Agent\Order_Letter.pdf")

if not pdf_path.exists():
    print(f"PDF not found: {pdf_path}")
else:
    try:
        pdf_bytes = pdf_path.read_bytes()
        extracted_text = extract_pdf_text(pdf_bytes)

        print("\n===== EXTRACTED PDF TEXT =====\n")
        print(extracted_text)

    except Exception as error:
        print(f"PDF extraction failed: {error}")
