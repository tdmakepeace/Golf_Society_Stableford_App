"""Render HTML to PDF bytes (used for competition results export)."""

from __future__ import annotations

from io import BytesIO

from xhtml2pdf import pisa


def html_to_pdf_bytes(html: str) -> bytes:
    buf = BytesIO()
    status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    if status.err:
        raise RuntimeError("PDF generation failed")
    return buf.getvalue()
