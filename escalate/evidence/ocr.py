"""Local text extraction: Tesseract for images, pypdf for PDFs, `email` for .eml. No cloud calls."""

import email
import io
import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage

import pytesseract
from PIL import Image
from pypdf import PdfReader

from escalate.config import Settings, get_settings
from escalate.db.models import Evidence

REVIEW_BELOW = 60.0  # mean Tesseract confidence (0-100)
MAX_TEXT = 200_000  # characters kept from one file
MAX_PDF_PAGES = 300
MAX_IMAGE_PIXELS = 40_000_000  # ~ 8000 x 5000: far above any phone screenshot or scan

# Defence in depth for files stored before upload checks (evidence/sniff.py): Pillow raises
# DecompressionBombError above twice this, which the OSError handler below does not catch.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@dataclass
class ExtractResult:
    text: str
    confidence: float | None = None  # only for OCR
    needs_review: bool = False


def extract_text(
    evidence: Evidence, settings: Settings | None = None, data: bytes | None = None
) -> ExtractResult:
    s = settings or get_settings()
    if data is None:
        from escalate.evidence.store import load_plain

        data = load_plain(evidence, s)
    return extract_bytes(evidence.kind, data, s.ocr_langs, s.ocr_timeout_s)


def extract_bytes(kind: str, data: bytes, langs: str, timeout: int = 0) -> ExtractResult:
    """Text from an upload's bytes. Slow (OCR, PDF parsing): call it off the event loop."""
    match kind:
        case "image":
            return _image(data, langs, timeout)
        case "pdf":
            return _pdf(data)
        case "email":
            return ExtractResult(_eml(data)[:MAX_TEXT])
        case "text":
            return ExtractResult(data.decode("utf-8", errors="replace")[:MAX_TEXT])
        case _:
            return ExtractResult("", needs_review=True)


def _image(data: bytes, langs: str, timeout: int = 0) -> ExtractResult:
    try:
        img = Image.open(io.BytesIO(data))
        d = pytesseract.image_to_data(
            img, lang=langs, output_type=pytesseract.Output.DICT, timeout=timeout
        )
    except (
        RuntimeError,  # pytesseract's timeout
        pytesseract.TesseractNotFoundError,
        pytesseract.TesseractError,
        OSError,
        Image.DecompressionBombError,
    ):
        return ExtractResult("", confidence=0.0, needs_review=True)

    lines: dict[tuple[int, int, int], list[str]] = {}
    confs: list[float] = []
    for i, word in enumerate(d["text"]):
        conf = float(d["conf"][i])
        if not word.strip() or conf < 0:
            continue
        confs.append(conf)
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    mean = sum(confs) / len(confs) if confs else 0.0
    return ExtractResult(text, confidence=round(mean, 1), needs_review=mean < REVIEW_BELOW)


def _pdf(data: bytes) -> ExtractResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = list(reader.pages)[:MAX_PDF_PAGES]
        text = "\n".join((page.extract_text() or "") for page in pages).strip()[:MAX_TEXT]
    except Exception:  # malformed PDFs raise many different errors
        return ExtractResult("", needs_review=True)
    # A PDF with no text layer is a scan: ask the user to check it.
    return ExtractResult(text, needs_review=not text)


def _eml(data: bytes) -> str:
    msg = email.message_from_bytes(data, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    header = "\n".join(f"{h}: {msg[h]}" for h in ("From", "To", "Date", "Subject") if msg[h])
    part = msg.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part is not None else ""
    if part is not None and part.get_content_type() == "text/html":
        body = re.sub(r"<[^>]+>", " ", body)
    return f"{header}\n\n{body.strip()}"
