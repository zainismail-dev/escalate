"""Check an upload before it is stored: the bytes must really be the kind its name claims.

Evidence is screenshots, PDFs, emails and text. Executables, archives and anything whose magic
bytes do not match the extension are refused, and images are measured before OCR so a tiny file
that decompresses to gigapixels (a decompression bomb) never reaches Tesseract.
"""

import io
from pathlib import Path

from escalate.evidence.ocr import MAX_IMAGE_PIXELS, MAX_PDF_PAGES
from escalate.evidence.store import kind_for


class UploadRejected(ValueError):
    """The file is not evidence Escalate accepts. The message is safe to show the user."""


# (magic prefix, what it is). Checked before anything else.
_FORBIDDEN: list[tuple[bytes, str]] = [
    (b"MZ", "a Windows program"),
    (b"\x7fELF", "a Linux program"),
    (b"\xcf\xfa\xed\xfe", "a macOS program"),
    (b"\xce\xfa\xed\xfe", "a macOS program"),
    (b"\xca\xfe\xba\xbe", "a macOS or Java program"),
    (b"#!", "a script"),
    (b"PK\x03\x04", "a zip archive"),
    (b"PK\x05\x06", "a zip archive"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"7z\xbc\xaf\x27\x1c", "a 7-Zip archive"),
    (b"Rar!\x1a\x07", "a RAR archive"),
    (b"BZh", "a bzip2 archive"),
    (b"\xfd7zXZ\x00", "an xz archive"),
    (b"\x28\xb5\x2f\xfd", "a zstd archive"),
    (b"MSCF", "a cabinet archive"),
    (b"\xd0\xcf\x11\xe0", "an Office/OLE file (can carry macros)"),
]

_IMAGE_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": (b"BM",),
}


def _is_tar(data: bytes) -> bool:
    return len(data) > 262 and data[257:262] == b"ustar"


def _check_image(suffix: str, data: bytes) -> None:
    if suffix == ".webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        ok = data.startswith(_IMAGE_MAGIC[suffix])
    if not ok:
        raise UploadRejected(f"this file is not a {suffix[1:].upper()} image")
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:  # reads the header only, no decoding
            width, height = img.size
    except Exception as exc:  # Pillow raises many types for broken files
        raise UploadRejected("this image could not be read") from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise UploadRejected(
            f"this image is too large ({width} x {height} pixels); "
            f"the limit is {MAX_IMAGE_PIXELS // 1_000_000} megapixels"
        )


def _check_pdf(data: bytes) -> None:
    if not data[:1024].lstrip().startswith(b"%PDF-"):
        raise UploadRejected("this file is not a PDF")
    from pypdf import PdfReader

    try:
        pages = len(PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:  # malformed PDFs raise many different errors
        raise UploadRejected("this PDF could not be read") from exc
    if pages > MAX_PDF_PAGES:
        raise UploadRejected(f"this PDF has {pages} pages; the limit is {MAX_PDF_PAGES}")


def _check_text(data: bytes, what: str) -> None:
    """Emails may be in any 8-bit charset (their headers say which); text files must be UTF-8."""
    if b"\x00" in data:
        raise UploadRejected(f"this file is not {what} (it contains binary data)")
    if what == "a text file":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected("this text file is not UTF-8; save it as UTF-8") from exc


def check_upload(filename: str, data: bytes) -> str:
    """The evidence kind for an acceptable upload; raises UploadRejected otherwise."""
    for magic, what in _FORBIDDEN:
        if data.startswith(magic):
            raise UploadRejected(f"this looks like {what}; upload a screenshot, PDF or email")
    if _is_tar(data):
        raise UploadRejected("this looks like a tar archive; upload a screenshot, PDF or email")
    suffix = Path(filename).suffix.lower()
    kind = kind_for(filename)
    match kind:
        case "image":
            _check_image(suffix, data)
        case "pdf":
            _check_pdf(data)
        case "email":
            _check_text(data, "an email")
        case "text":
            _check_text(data, "a text file")
        case _:
            raise UploadRejected(
                "unsupported file type; upload an image (PNG, JPG, WebP, GIF, TIFF, BMP), "
                "a PDF, an email (.eml) or a text file"
            )
    return kind
