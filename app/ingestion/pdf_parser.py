import pymupdf as fitz
import pdfplumber

from app.ingestion.vision_captioner import caption_chart_image

Unit = tuple[str, dict]

_IMAGE_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

# Small images are almost always logos/icons/bullets, not charts worth captioning,
# and captioning every one would waste API calls and can fail on odd formats.
_MIN_IMAGE_DIMENSION = 100

# Guard against PDFs with dozens of images; each vision API call adds ~10-30 s.
_MAX_IMAGES_PER_PDF = 5


def parse_pdf(file_path: str, filename: str) -> list[Unit]:
    """Extracts text, tables, and captions chart/photo images per page.

    Returns a list of (text, metadata) units, one per logical section (text block,
    table, or chart caption), each tagged with its source page number.
    """
    units: list[Unit] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                units.append((text, {"source": filename, "page": page_num, "type": "text"}))

            for table in page.extract_tables():
                rows = ["\t".join(cell or "" for cell in row) for row in table]
                table_text = "\n".join(rows).strip()
                if table_text:
                    units.append((table_text, {"source": filename, "page": page_num, "type": "table"}))

    # Images (charts/photos) are extracted separately via PyMuPDF and captioned by a vision LLM,
    # since plain text extraction cannot see what's inside a rendered chart. A failure on any
    # single image (unsupported format, API hiccup) must not abort ingestion of the whole document.
    doc = fitz.open(file_path)
    images_captioned = 0
    for page_index in range(len(doc)):
        if images_captioned >= _MAX_IMAGES_PER_PDF:
            print(f"INFO: reached {_MAX_IMAGES_PER_PDF}-image cap for {filename}; skipping remaining images.")
            break
        page = doc[page_index]
        for image in page.get_images(full=True):
            if images_captioned >= _MAX_IMAGES_PER_PDF:
                break
            xref = image[0]
            try:
                base_image = doc.extract_image(xref)
                width, height = base_image.get("width", 0), base_image.get("height", 0)
                if width < _MIN_IMAGE_DIMENSION or height < _MIN_IMAGE_DIMENSION:
                    continue
                image_bytes = base_image["image"]
                mime_type = _IMAGE_EXT_MIME.get(base_image.get("ext", "png"), "image/png")
                caption = caption_chart_image(image_bytes, mime_type).strip()
                images_captioned += 1
            except Exception as exc:
                print(f"WARNING: skipping image xref={xref} on page {page_index + 1} of {filename}: {exc}")
                continue
            if caption:
                units.append(
                    (caption, {"source": filename, "page": page_index + 1, "type": "chart"})
                )
    doc.close()

    return units


def get_page_count(file_path: str) -> int:
    with pdfplumber.open(file_path) as pdf:
        return len(pdf.pages)
