"""Regenerate the small evidence fixtures: uv run python tests/fixtures/make_fixtures.py"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent

RECEIPT_LINES = [
    "BRIGHTMART ELECTRONICS",
    "Order ID: BM-48213",
    "Date: 2026-02-14",
    "LED TV 43 inch",
    "Total: 45000 PKR",
]


def receipt_png() -> None:
    font = ImageFont.load_default(size=36)
    img = Image.new("L", (900, 420), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(RECEIPT_LINES):
        draw.text((40, 30 + i * 75), line, fill=0, font=font)
    img.save(HERE / "receipt.png")


def receipt_pdf() -> None:
    """A minimal one-page PDF with a real text layer, written by hand (no extra deps)."""
    text_ops = "BT /F1 14 Tf 72 720 Td 18 TL " + " ".join(
        f"({line}) Tj T*" for line in RECEIPT_LINES
    )
    stream = text_ops + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = "%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    (HERE / "receipt.pdf").write_bytes(out.encode("latin-1"))


def seller_eml() -> None:
    (HERE / "seller_reply.eml").write_text(
        "From: Support <support@brightmart.example>\n"
        "To: Buyer <buyer@example.com>\n"
        "Date: Mon, 16 Mar 2026 10:00:00 +0500\n"
        "Subject: Re: Order BM-48213 defective LED\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Dear customer, we will replace the LED when the company claim is approved.\n"
    )


if __name__ == "__main__":
    receipt_png()
    receipt_pdf()
    seller_eml()
