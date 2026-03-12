"""OCR fallback for scanned PDF drawings using Tesseract."""

from __future__ import annotations

from pathlib import Path

from drawmind.config import OCR_DPI, OCR_CONFIDENCE_THRESHOLD


def ocr_page_tesseract(pdf_path: str | Path, page_num: int = 0, dpi: int = OCR_DPI) -> list[dict]:
    """OCR a PDF page using Tesseract and return text with bounding boxes.

    Args:
        pdf_path: Path to the PDF
        page_num: Page number to process
        dpi: Resolution for rendering

    Returns:
        List of dicts with text, bbox, page, source, confidence
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io
    except ImportError as e:
        raise ImportError(f"OCR requires pytesseract and Pillow: {e}")

    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()

    img = Image.open(io.BytesIO(img_bytes))

    # Run Tesseract with sparse text mode (good for drawings)
    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config="--psm 11 --oem 3",
    )

    results = []
    scale = 72.0 / dpi  # Convert pixel coords to PDF points

    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])

        if text and conf > OCR_CONFIDENCE_THRESHOLD:
            results.append({
                "text": text,
                "bbox": {
                    "x0": data["left"][i] * scale,
                    "y0": data["top"][i] * scale,
                    "x1": (data["left"][i] + data["width"][i]) * scale,
                    "y1": (data["top"][i] + data["height"][i]) * scale,
                },
                "page": page_num,
                "source": "ocr",
                "confidence": conf / 100.0,
            })

    return results
