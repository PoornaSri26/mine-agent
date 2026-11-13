"""Render the audit agent's markdown briefing as a paginated A4 PDF."""

from __future__ import annotations

import io
import re

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_LATIN = re.compile(r"[^\x09\x0a\x0d\x20-\x7e\u00a0-\u00ff]")


def _clean(text: str) -> str:
    """ReportLab's built-in fonts only cover Latin-1; drop what they cannot draw."""
    return _LATIN.sub("", text)


def _inline(text: str) -> str:
    """Convert the small markdown subset the agents emit into ReportLab XML."""
    escaped = (
        _clean(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", escaped)
    return escaped


def build_report_pdf(title: str, meta: dict[str, str], body: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="MineRakshak multi-agent service",
    )

    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=6)
    subtitle = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, leading=12, textColor="#555555", spaceAfter=4)
    section = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14, alignment=TA_LEFT)
    bullet_style = ParagraphStyle("bullet", parent=body_style, leftIndent=12, bulletIndent=2, spaceAfter=2)

    flowables = [Paragraph(_inline(title), heading)]
    for label, value in meta.items():
        flowables.append(Paragraph(_inline(f"<b>{label}:</b> {value}"), subtitle))
    flowables.append(Spacer(1, 8))

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 5))
            continue
        bold_only = re.fullmatch(r"\*\*(.+?)\*\*", line)
        if bold_only:
            flowables.append(Paragraph(_inline(bold_only.group(1)), section))
            continue
        numbered = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if numbered:
            flowables.append(Paragraph(_inline(numbered.group(2)), bullet_style, bulletText=f"{numbered.group(1)}."))
            continue
        if line.startswith(("- ", "• ")):
            flowables.append(Paragraph(_inline(line[2:]), bullet_style, bulletText="•"))
            continue
        if line.startswith("#"):
            flowables.append(Paragraph(_inline(line.lstrip("# ").strip()), section))
            continue
        flowables.append(Paragraph(_inline(line), body_style))

    doc.build(flowables)
    return buffer.getvalue()
