
from io import BytesIO

import pymupdf
import pytesseract
from PIL import Image


# Set the Tesseract executable path on Windows.
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract text from a PDF.
    Uses normal text extraction first and OCR for scanned pages.
    """

    if not pdf_bytes:
        raise ValueError("The PDF file is empty.")

    extracted_pages = []

    with pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    ) as pdf:

        if pdf.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")

        for page_number, page in enumerate(pdf, start=1):

            # First, try extracting selectable text.
            text = page.get_text().strip()

            # If the page has no selectable text, use OCR.
            if not text:
                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(2, 2),
                    alpha=False
                )

                image = Image.open(
                    BytesIO(pix.tobytes("png"))
                )

                text = pytesseract.image_to_string(
                    image,
                    lang="eng",
                    config="--psm 6"
                ).strip()

            # Store the extracted text for this page.
            if text:
                extracted_pages.append(
                    f"Page {page_number}:\n{text}"
                )

    result = "\n\n".join(extracted_pages).strip()

    if not result:
        raise ValueError(
            "No text could be extracted from the PDF."
        )

    return result
