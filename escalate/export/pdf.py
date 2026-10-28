"""HTML -> PDF with WeasyPrint (needs the Pango system library)."""

import html
import re
from functools import lru_cache

from escalate.i18n.countries import is_rtl


class PdfUnavailable(RuntimeError):
    pass


@lru_cache
def pdf_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        return False
    return True


def html_to_pdf(document: str) -> bytes:
    if not pdf_available():
        raise PdfUnavailable(
            "WeasyPrint cannot load its system libraries (Pango). Install them, or use Docker."
        )
    from weasyprint import HTML

    pdf = HTML(string=document).write_pdf()
    assert pdf is not None
    return bytes(pdf)


def text_to_html(text: str) -> str:
    """Plain/Markdown-ish letter text -> safe HTML paragraphs (no Markdown dependency)."""
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for block in blocks:
        if block.strip() == "---":
            out.append("<hr>")
            continue
        lines = [html.escape(line) for line in block.split("\n")]
        out.append("<p>" + "<br>".join(lines) + "</p>")
    return "\n".join(out)


LETTER_CSS = """
@page { size: A4; margin: 22mm 20mm; }
body { font-family: "DejaVu Serif", "Noto Serif", Georgia, serif; font-size: 11.5pt;
       line-height: 1.45; color: #111; }
h1 { font-size: 13pt; margin: 0 0 12pt; }
hr { border: 0; border-top: 1px solid #999; margin: 14pt 0; }
p { margin: 0 0 9pt; }
"""


def letter_pdf(subject: str | None, body: str, lang: str = "en") -> bytes:
    title = f"<h1>{html.escape(subject)}</h1>" if subject else ""
    direction = "rtl" if is_rtl(lang) else "ltr"
    doc = (
        f'<!doctype html><html lang="{html.escape(lang)}" dir="{direction}"><head>'
        f'<meta charset="utf-8"><style>{LETTER_CSS}</style></head>'
        f"<body>{title}{text_to_html(body)}</body></html>"
    )
    return html_to_pdf(doc)
