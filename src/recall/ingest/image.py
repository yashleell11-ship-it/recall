"""Image ingest for photos of notes, slides and textbook pages.

OCR happens in exactly one function, `extract_text_from_image`, so a
vision-capable API can replace Tesseract later by changing this file and
nothing else. Everything downstream sees the same `[(page, text)]` shape a PDF
produces.
"""

from PIL import Image, ImageOps

# Phone cameras produce 12-50 MP files. Tesseract is much slower on those
# without reading them any better, and a downscale to a 3000px long edge still
# leaves body text far above the ~20px glyph height Tesseract needs.
MAX_LONG_EDGE = 3000

# Below this much text the OCR almost certainly failed rather than the page
# being empty. Scaled by area because a 12 MP photo of a page should yield
# thousands of characters while a small screenshot legitimately yields few.
MIN_CHARS = 40
CHARS_PER_MEGAPIXEL = 40.0

SPARSE_WARNING = "very little text found, handwriting may not OCR well"


class OcrUnavailable(RuntimeError):
    """The Tesseract binary is missing. A configuration fault, not bad input."""


def _tesseract(image: Image.Image) -> str:
    # Imported here so the rest of the package loads on a machine without OCR.
    import pytesseract

    try:
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailable(
            "tesseract is not installed on this machine, so images cannot be "
            "read yet. Install the tesseract binary, or upload a PDF or text file."
        ) from exc


def load_for_ocr(path: str) -> Image.Image:
    """Open an image in the form Tesseract reads best: upright, not enormous."""
    with Image.open(path) as raw:
        # A phone stores the sensor pixels unrotated and records the rotation in
        # EXIF. Skipping this reads a sideways page and returns near-nothing,
        # which later looks like a mystery OCR bug rather than a missing rotate.
        image = ImageOps.exif_transpose(raw)

    long_edge = max(image.size)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        width, height = image.size
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.LANCZOS,
        )
    # Grayscale: what Tesseract binarises anyway, and it drops any alpha channel
    # that would otherwise render as black.
    return image.convert("L")


def extract_text_from_image(path: str, ocr=_tesseract) -> str:
    """The one place OCR happens. `ocr` takes a PIL image and returns text."""
    image = load_for_ocr(path)
    try:
        return ocr(image).strip()
    finally:
        image.close()


def image_pixel_count(path: str) -> int:
    with Image.open(path) as image:
        width, height = image.size
    return width * height


def sparse_text_warning(text: str, pixels: int) -> str | None:
    """Say plainly when the text is too thin for the image to be believable.

    Three bad cards from a photo of a whiteboard is worse than being told the
    photo did not read.
    """
    chars = len(text.strip())
    megapixels = pixels / 1_000_000
    expected = max(MIN_CHARS, CHARS_PER_MEGAPIXEL * megapixels)
    if chars >= expected:
        return None
    return (
        f"{SPARSE_WARNING} — {chars} characters from a {megapixels:.1f} MP image"
    )
