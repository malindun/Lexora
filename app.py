"""
AI-Powered Document & UI Layout Reconstructor — Dual PDF Edition v4
====================================================================
Generates TWO PDFs from any uploaded image:
  1. Exact Replica  — faithful visual clone of the source (notebook/form style)
  2. Enhanced       — rich colors, icons, visual design — SAME WORDS ONLY

Rules for Enhanced:
  - Zero extra words beyond those in the source image
  - Rich colors, icons (Unicode symbols added to keys), bold typography
  - Smart page-fill: content is scaled/spaced to fill the chosen paper size

User can choose: A4, Letter, A3, Legal, A5

Requirements:
    pip install streamlit google-genai reportlab Pillow
"""

import io
import json
import math
import re
import time
import traceback
from datetime import datetime

import streamlit as st
from PIL import Image

# ── ReportLab imports ────────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, A5, LETTER, LEGAL
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm, pt
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Google GenAI import ──────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    st.error("❌ `google-genai` not found. Run: pip install google-genai")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Doc Reconstructor · Dual PDF Engine",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Page size registry ────────────────────────────────────────────────────────
PAGE_SIZES = {
    "A4  (210 × 297 mm)":     A4,
    "Letter (216 × 279 mm)":  LETTER,
    "A3  (297 × 420 mm)":     A3,
    "Legal (216 × 356 mm)":   LEGAL,
    "A5  (148 × 210 mm)":     A5,
}

# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM CSS
# ═══════════════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #020617 !important;
    color: #e2e8f0 !important;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}
[data-testid="stApp"],
[data-testid="stMain"] { background-color: #020617 !important; }
.main .block-container {
    background-color: #020617 !important;
    padding-top: 2rem;
    padding-bottom: 2rem;
}
[data-testid="stSidebar"] {
    background-color: #0f172a !important;
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
[data-testid="stSidebar"] .stTextInput > div > div > input {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
    border-radius: 8px;
}
[data-testid="stSidebar"] .stTextInput > div > div > input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.25) !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #f1f5f9 !important; }
[data-testid="stFileUploader"] {
    background-color: #0f172a !important;
    border: 2px dashed #334155 !important;
    border-radius: 12px !important;
    padding: 1rem;
}
[data-testid="stFileUploader"]:hover { border-color: #3b82f6 !important; }
[data-testid="stFileUploader"] * { color: #94a3b8 !important; }
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8, #2563eb) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important;
    width: 100%;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #1e40af, #1d4ed8) !important;
    box-shadow: 0 6px 18px rgba(37,99,235,0.5) !important;
    transform: translateY(-1px) !important;
}
.stDownloadButton > button {
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-weight: 600 !important;
    width: 100%;
    transition: all 0.2s ease !important;
    color: #fff !important;
}
.stDownloadButton > button:hover { transform: translateY(-1px) !important; }
.stAlert { border-radius: 10px !important; border: none !important; }
.doc-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}
.doc-card h3 {
    color: #f1f5f9;
    margin-top: 0;
    margin-bottom: 0.5rem;
    font-size: 1rem;
    font-weight: 600;
}
.doc-card p { color: #64748b; margin: 0; font-size: 0.875rem; line-height: 1.6; }
.pdf-card-exact {
    background: #0f172a;
    border: 1px solid #334155;
    border-top: 3px solid #475569;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}
.pdf-card-enhanced {
    background: #0a1f1a;
    border: 1px solid #065f46;
    border-top: 3px solid #10b981;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}
.stat-badge {
    display: inline-block;
    background: #1e293b;
    border: 1px solid #334155;
    color: #94a3b8;
    border-radius: 20px;
    padding: 0.25rem 0.85rem;
    font-size: 0.78rem;
    font-weight: 500;
    margin-right: 0.4rem;
    margin-top: 0.3rem;
}
.stat-badge span { color: #3b82f6; font-weight: 700; }
[data-testid="stExpander"] {
    background-color: #0f172a !important;
    border: 1px solid #1e293b !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}
[data-testid="stImage"] img {
    border-radius: 10px !important;
    border: 1px solid #1e293b !important;
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0f172a; }
::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #475569; }
hr {
    border: none !important;
    border-top: 1px solid #1e293b !important;
    margin: 1.5rem 0 !important;
}
[data-testid="stSelectbox"] > div > div {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📄 Doc Reconstructor")
    st.markdown(
        "<p style='color:#64748b; font-size:0.82rem; margin-top:-0.5rem;'>"
        "Dual PDF Engine · v4.0</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### 🔑 API Configuration")
    api_key = st.text_input(
        "Google AI Studio API Key",
        type="password",
        placeholder="AIza...",
        help="https://aistudio.google.com/",
    )
    if not api_key:
        st.info(
            "🔐 **API Key Required**\n\n"
            "Enter your Google AI Studio API key above.\n\n"
            "👉 [Get a free key →](https://aistudio.google.com/)"
        )

    st.markdown("---")
    st.markdown("### ⚙️ PDF Settings")

    pdf_title = st.text_input(
        "Document Title (optional)",
        placeholder="e.g. Meeting Agenda",
        value="",
    )

    page_size_label = st.selectbox(
        "📐 Paper Size",
        list(PAGE_SIZES.keys()),
        index=0,
        help="Applied to both PDFs",
    )
    chosen_page_size = PAGE_SIZES[page_size_label]

    st.markdown("---")
    st.markdown("### 📋 What you get")
    for icon, label in [
        ("🖨️", "Exact Replica — notebook visual style"),
        ("✨", "Enhanced — rich design, same words only"),
        ("📐", "Chosen paper size, content fills the page"),
        ("🎨", "Icons, bold colors, banner, typography"),
    ]:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:0.6rem;"
            f"margin-bottom:0.4rem;'>"
            f"<span style='font-size:1rem;'>{icon}</span>"
            f"<span style='color:#94a3b8; font-size:0.82rem;'>{label}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        "<p style='color:#334155; font-size:0.72rem; text-align:center;'>"
        "Gemini 2.5 Flash · ReportLab · Streamlit</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RETRY WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

def generate_content_with_retry(client, model, contents, max_retries=5):
    """Exponential-backoff retry for transient API failures (503, 429, 500)."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception as exc:
            last_exc = exc
            err = str(exc).lower()
            if not any(c in err for c in ["503", "unavailable", "resource exhausted", "429", "500"]):
                raise
            wait = 2 ** attempt
            if attempt < max_retries - 1:
                st.toast(f"⚠️ API busy — retry in {wait}s ({attempt+1}/{max_retries})", icon="🔄")
                time.sleep(wait)
    raise last_exc


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def extract_elements_safely(raw: str) -> list:
    """Multi-stage JSON parser resilient to markdown wrapping and minor corruption."""
    if not raw or not raw.strip():
        raise ValueError("Empty AI response.")
    text = raw.strip()

    # Stage 1: direct parse
    try:
        p = json.loads(text)
        if isinstance(p, list):
            return p
        if isinstance(p, dict):
            for v in p.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # Stage 2: extract [...] block
    try:
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            p = json.loads(m.group(0))
            if isinstance(p, list):
                return p
    except Exception:
        pass

    # Stage 3: strip markdown fences and retry
    try:
        cleaned = re.sub(r'```(?:json|python)?\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()
        p = json.loads(cleaned)
        if isinstance(p, list):
            return p
        m = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if m:
            p = json.loads(m.group(0))
            if isinstance(p, list):
                return p
    except Exception:
        pass

    raise ValueError(f"JSON parse failed. Preview: {raw[:300]}")


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_EXACT = (
    "You are an elite Document Layout Specialist.\n"
    "Reconstruct the COMPLETE visual content of the image into a structured JSON array.\n\n"
    "RULES:\n"
    "- Preserve EXACT reading order top-to-bottom, left-to-right.\n"
    "- Transcribe ALL text verbatim — no rephrasing, no summarising, no omitting.\n"
    "- Match heading hierarchy EXACTLY as shown (title style, section headers).\n"
    "- For numbered/bulleted lists: each numbered item must be its OWN paragraph element "
    "with the number included in the text field "
    "(e.g. '1. Review of last month performance').\n"
    "- For 'Date:', 'Time:', 'Venue:' style lines use key_value_pair with the label as key "
    "and the value as value (e.g. key='Date', value='10 November 2026').\n"
    "- Preserve separator lines visible in the image as separator elements.\n"
    "- Do NOT skip any element. Do NOT add anything not visible in the image.\n\n"
    "ELEMENT TYPES (use ONLY these):\n"
    '{ "type": "heading",        "text": "...", "level": 1 }\n'
    '{ "type": "subheading",     "text": "...", "level": 2 }\n'
    '{ "type": "paragraph",      "text": "..." }\n'
    '{ "type": "separator" }\n'
    '{ "type": "key_value_pair", "key": "...", "value": "..." }\n'
    '{ "type": "table",          "headers": [...], "rows": [[...], ...] }\n\n'
    "OUTPUT: Return ONLY a raw JSON array [ ... ]. "
    "No markdown, no backticks, no explanation.\n"
    "Analyze the image now:"
)

PROMPT_ENHANCED = (
    "You are a Visual Document Designer.\n"
    "Analyze the image and output a structured JSON array for a richly designed PDF.\n\n"
    "CRITICAL WORD RULE:\n"
    "- You may use ONLY words, numbers, and punctuation that appear in the source image.\n"
    "- Do NOT add any new words, labels, sentences, or descriptions not present in the image.\n"
    "- You MAY: reorder fields, group items, assign icon prefixes, change visual hierarchy.\n"
    "- ZERO new vocabulary beyond what is already in the image.\n\n"
    "ICON PREFIX RULE — prepend one Unicode icon to KEY fields of key_value_pair only:\n"
    "  📅 for dates   🕐 for times   📍 for locations/venues   👤 for person/name\n"
    "  📋 for reference/number   📧 for email   📞 for phone   🏢 for company/org\n"
    "  📁 for file/document   ✅ for status   🔖 for category\n"
    "For keys that do not match, use no icon prefix.\n"
    "NEVER add icons to heading, subheading, or paragraph text.\n\n"
    "STRUCTURE GUIDANCE:\n"
    "- Group related key_value_pairs together between separators.\n"
    "- Use separator elements generously between logical sections.\n"
    "- Subheadings should precede their content group.\n"
    "- The main title must be a heading level 1.\n"
    "- Each numbered list item should be its own paragraph element "
    "(keep the number prefix).\n\n"
    "ELEMENT TYPES (use ONLY these):\n"
    '{ "type": "heading",        "text": "...", "level": 1 }\n'
    '{ "type": "subheading",     "text": "...", "level": 2 }\n'
    '{ "type": "paragraph",      "text": "..." }\n'
    '{ "type": "separator" }\n'
    '{ "type": "key_value_pair", "key": "...", "value": "..." }\n'
    '{ "type": "table",          "headers": [...], "rows": [[...], ...] }\n\n'
    "OUTPUT: Return ONLY a raw JSON array [ ... ]. "
    "No markdown, no backticks, no explanation.\n"
    "Analyze the image now:"
)


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI CALL
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_image(api_key: str, image_bytes: bytes, mime_type: str, prompt: str):
    """Send image + prompt to Gemini, return (elements list, raw text)."""
    client    = genai.Client(api_key=api_key)
    img_part  = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    text_part = genai_types.Part.from_text(text=prompt)
    contents  = [genai_types.Content(parts=[img_part, text_part], role="user")]
    resp      = generate_content_with_retry(client, "gemini-2.5-flash", contents)
    elements  = extract_elements_safely(resp.text)
    return elements, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE-FILL SCALING UTILITY
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_story_height(elements: list, usable_w: float) -> float:
    """
    Rough vertical height estimate for a list of elements.
    Used only to compute a fill-scale factor — exact precision not required.
    """
    total = 0.0
    for elem in elements:
        t = elem.get("type", "")
        if t == "heading":
            total += 40
        elif t == "subheading":
            total += 32
        elif t == "paragraph":
            text = str(elem.get("text", ""))
            cpl  = max(1, int(usable_w / 6.5))
            lines = max(1, math.ceil(len(text) / cpl))
            total += lines * 16 + 10
        elif t == "separator":
            total += 22
        elif t == "key_value_pair":
            total += 26
        elif t == "table":
            rows = elem.get("rows", [])
            total += (len(rows) + 1) * 24 + 20
        else:
            total += 18
    return max(total, 1.0)


def compute_fill_scale(story_h: float, usable_h: float) -> float:
    """
    Returns a scale factor >= 1.0 so content expands to fill the usable page height.
    Capped at 3.5 to avoid absurdly large text.
    """
    if story_h <= 0 or usable_h <= 0:
        return 1.0
    return max(1.0, min(usable_h / story_h, 3.5))


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE BUILDER (shared by both PDF modes)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_col_widths(num_cols: int, usable_w: float) -> list:
    presets = {
        1: [1.0],
        2: [0.38, 0.62],
        3: [0.23, 0.35, 0.42],
        4: [0.18, 0.23, 0.23, 0.36],
        5: [0.15, 0.19, 0.15, 0.19, 0.32],
        6: [0.125, 0.183, 0.106, 0.125, 0.144, 0.317],
    }
    ratios = presets.get(num_cols, [1.0 / num_cols] * num_cols)
    widths = [round(r * usable_w, 2) for r in ratios]
    widths[-1] = round(usable_w - sum(widths[:-1]), 2)
    return widths


def build_table(element, th_sty, tc_sty,
                hdr_bg, hdr_fg, row_odd, row_even, grid_col,
                usable_w, row_pad=5, font_size=9):
    """Construct a ReportLab Table flowable from a table element dict."""
    headers  = element.get("headers", []) or ["Column"]
    raw_rows = element.get("rows", [])
    nc       = len(headers)
    col_w    = compute_col_widths(nc, usable_w)

    hdr_cells = [Paragraph(str(h), th_sty) for h in headers]
    data_rows = []
    for row in raw_rows:
        padded = list(row) + [""] * max(0, nc - len(row))
        data_rows.append([Paragraph(str(c), tc_sty) for c in padded[:nc]])

    tbl = Table([hdr_cells] + data_rows, colWidths=col_w, repeatRows=1)
    ts  = [
        ("BACKGROUND",    (0, 0), (-1, 0),  hdr_bg),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  hdr_fg),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  font_size),
        ("TOPPADDING",    (0, 0), (-1, 0),  row_pad + 2),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  row_pad + 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), font_size),
        ("TOPPADDING",    (0, 1), (-1, -1), row_pad),
        ("BOTTOMPADDING", (0, 1), (-1, -1), row_pad),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.5, grid_col),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, hdr_bg),
    ]
    for i in range(1, len(data_rows) + 1):
        bg = row_odd if i % 2 == 1 else row_even
        ts.append(("BACKGROUND", (0, i), (-1, i), bg))
    tbl.setStyle(TableStyle(ts))
    return tbl


# ═══════════════════════════════════════════════════════════════════════════════
# PDF 1 — EXACT REPLICA
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Visual targets from the reference image (lined notebook):
#   • Off-white / cream paper background
#   • Thin horizontal blue ruled lines across the full page
#   • Pink/red vertical margin line on the left
#   • Title centered in a double-line bordered box at the top
#   • Key-value pairs: "Key:   Value" inline on ruled lines
#   • Numbered list items as plain text on ruled lines
#   • Courier body font (handwritten / typewriter feel)
# ──────────────────────────────────────────────────────────────────────────────

C_EX_PAPER    = colors.HexColor("#fdfdf5")   # cream notebook paper
C_EX_LINES    = colors.HexColor("#b8d4e8")   # light blue ruled lines
C_EX_MARGIN   = colors.HexColor("#e57373")   # red/pink margin line
C_EX_TITLE_FG = colors.HexColor("#c62828")   # dark red title text
C_EX_TITLE_BG = colors.HexColor("#fce4ec")   # light pink title background
C_EX_TITLE_BD = colors.HexColor("#e53935")   # title box border
C_EX_KEY      = colors.HexColor("#1a237e")   # dark navy key text
C_EX_BODY     = colors.HexColor("#1a1a2e")   # near-black body text
C_EX_SEP      = colors.HexColor("#90a4ae")   # separator line color
C_EX_H2       = colors.HexColor("#1a237e")   # subheading color
C_EX_THBG     = colors.HexColor("#37474f")
C_EX_THFG     = colors.white
C_EX_ODD      = colors.HexColor("#f5f5f5")
C_EX_EVEN     = colors.HexColor("#eceff1")
C_EX_GRID     = colors.HexColor("#cfd8dc")

MARGIN_LINE_X = 55   # x-coordinate of the red vertical margin line


def _draw_exact_page(c: rl_canvas.Canvas, doc, page_size: tuple):
    """
    Draw the notebook background on every page:
      1. Cream fill
      2. Horizontal light-blue ruled lines (every 22 pt)
      3. Red/pink vertical margin line
    """
    pw, ph = page_size
    line_spacing = 22   # points between ruled lines

    # Cream background
    c.setFillColor(C_EX_PAPER)
    c.rect(0, 0, pw, ph, stroke=0, fill=1)

    # Horizontal ruled lines
    c.setStrokeColor(C_EX_LINES)
    c.setLineWidth(0.6)
    y = ph - 30
    while y > 18:
        c.line(0, y, pw, y)
        y -= line_spacing

    # Red vertical margin line
    c.setStrokeColor(C_EX_MARGIN)
    c.setLineWidth(1.5)
    c.line(MARGIN_LINE_X, 0, MARGIN_LINE_X, ph)


def exact_styles(s: float = 1.0) -> dict:
    """
    Build ParagraphStyles for the exact replica.
    s = scale factor so content expands to fill the chosen page size.
    Courier is used for body text to evoke the handwritten/typewritten feel.
    """
    return {
        # Main title: centered, dark red, bold Helvetica
        "h1": ParagraphStyle(
            "ExH1",
            fontName="Helvetica-Bold",
            fontSize=round(15 * s, 1),
            leading=round(20 * s, 1),
            textColor=C_EX_TITLE_FG,
            spaceBefore=round(8 * s, 1),
            spaceAfter=round(6 * s, 1),
            alignment=TA_CENTER,
        ),
        # Section subheading
        "h2": ParagraphStyle(
            "ExH2",
            fontName="Helvetica-Bold",
            fontSize=round(11 * s, 1),
            leading=round(16 * s, 1),
            textColor=C_EX_H2,
            spaceBefore=round(8 * s, 1),
            spaceAfter=round(4 * s, 1),
        ),
        # Normal body / paragraph: Courier, leading matches notebook line spacing
        "para": ParagraphStyle(
            "ExPara",
            fontName="Courier",
            fontSize=round(10 * s, 1),
            leading=round(22 * s, 1),
            textColor=C_EX_BODY,
            spaceBefore=0,
            spaceAfter=0,
        ),
        # Key in key-value pair (bold Courier, navy)
        "key": ParagraphStyle(
            "ExKey",
            fontName="Courier-Bold",
            fontSize=round(10 * s, 1),
            leading=round(22 * s, 1),
            textColor=C_EX_KEY,
        ),
        # Value in key-value pair
        "val": ParagraphStyle(
            "ExVal",
            fontName="Courier",
            fontSize=round(10 * s, 1),
            leading=round(22 * s, 1),
            textColor=C_EX_BODY,
        ),
        # Table header / cell
        "th": ParagraphStyle(
            "ExTH",
            fontName="Helvetica-Bold",
            fontSize=round(9 * s, 1),
            leading=round(12 * s, 1),
            textColor=C_EX_THFG,
        ),
        "tc": ParagraphStyle(
            "ExTC",
            fontName="Helvetica",
            fontSize=round(9 * s, 1),
            leading=round(12 * s, 1),
            textColor=C_EX_BODY,
        ),
    }


def _title_box_flowable(title_text: str, sty, usable_w: float, scale: float):
    """
    Render the title inside a bordered box (mimics the double-line box in the image).
    Returns a Table flowable styled with a pink background and red border.
    """
    cell = Paragraph(title_text, sty)
    tbl  = Table([[cell]], colWidths=[usable_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_EX_TITLE_BG),
        ("BOX",           (0, 0), (-1, -1), 1.8, C_EX_TITLE_BD),
        ("INNERGRID",     (0, 0), (-1, -1), 0.6, C_EX_TITLE_BD),
        ("TOPPADDING",    (0, 0), (-1, -1), round(9 * scale, 1)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), round(9 * scale, 1)),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def build_exact_pdf(elements: list, doc_title: str, page_size: tuple) -> bytes:
    """
    Build the Exact Replica PDF.
    Visually matches the source notebook/form image:
    cream paper + ruled lines + red margin + bordered title box.
    """
    pw, ph   = page_size
    margin_l = MARGIN_LINE_X + 10   # text starts just right of the red line
    margin_r = max(38, pw * 0.06)
    margin_t = max(38, ph * 0.06)
    margin_b = max(38, ph * 0.06)
    usable_w = pw - margin_l - margin_r
    usable_h = ph - margin_t - margin_b

    # Compute fill scale
    est_h = estimate_story_height(elements, usable_w)
    scale = compute_fill_scale(est_h, usable_h * 0.90)
    sty   = exact_styles(scale)

    def sp(n: float) -> Spacer:
        return Spacer(1, max(2, round(n * scale, 1)))

    def sep() -> HRFlowable:
        return HRFlowable(
            width="100%", thickness=0.8, color=C_EX_SEP,
            spaceBefore=round(4 * scale, 1),
            spaceAfter=round(6 * scale, 1),
        )

    story = []
    story.append(sp(6))

    # Determine the cover title
    cover_title = doc_title.strip()
    if not cover_title:
        cover_title = next(
            (e.get("text", "") for e in elements if e.get("type") == "heading"),
            ""
        )
    seen_cover = cover_title.strip().lower()

    # Draw title in bordered box
    if cover_title:
        story.append(_title_box_flowable(cover_title, sty["h1"], usable_w, scale))
        story.append(sp(10))

    # Render elements
    for elem in elements:
        t = elem.get("type", "").lower()

        if t == "heading":
            text = str(elem.get("text", "")).strip()
            if not text or text.strip().lower() == seen_cover:
                continue   # already drawn as title box
            lv = elem.get("level", 1)
            story.append(sp(4))
            if lv == 1:
                story.append(_title_box_flowable(text, sty["h1"], usable_w, scale))
            else:
                story.append(Paragraph(text, sty["h2"]))
            story.append(sp(4))

        elif t == "subheading":
            text = str(elem.get("text", "")).strip()
            if text:
                story.append(sp(4))
                story.append(Paragraph(text, sty["h2"]))
                story.append(sp(2))

        elif t == "paragraph":
            text = str(elem.get("text", "")).strip()
            if text:
                story.append(Paragraph(text, sty["para"]))

        elif t == "separator":
            story.append(sep())

        elif t == "key_value_pair":
            key = str(elem.get("key",   "")).strip()
            val = str(elem.get("value", "")).strip()
            if not key:
                continue
            # Render as "Key:   Value" inline on the ruled line
            kw = round(usable_w * 0.28, 1)
            vw = round(usable_w - kw - 4, 1)
            row = Table(
                [[Paragraph(f"{key}:", sty["key"]),
                  Paragraph(val,       sty["val"])]],
                colWidths=[kw, vw],
            )
            row.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",    (0, 0), (-1, -1), round(1 * scale, 1)),
                ("BOTTOMPADDING", (0, 0), (-1, -1), round(1 * scale, 1)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))
            story.append(row)

        elif t == "table":
            story.append(sp(6))
            story.append(build_table(
                elem, sty["th"], sty["tc"],
                C_EX_THBG, C_EX_THFG, C_EX_ODD, C_EX_EVEN, C_EX_GRID,
                usable_w,
                row_pad=round(5 * scale, 1),
                font_size=round(9 * scale, 1),
            ))
            story.append(sp(6))

        else:
            text = str(elem.get("text", elem.get("content", ""))).strip()
            if text:
                story.append(Paragraph(text, sty["para"]))

    # Build PDF with notebook background on every page
    buf = io.BytesIO()
    _ps = page_size

    def _draw_bg(c, doc):
        _draw_exact_page(c, doc, _ps)

    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        topMargin=margin_t,
        bottomMargin=margin_b,
        leftMargin=margin_l,
        rightMargin=margin_r,
        title=doc_title or "Exact Replica",
        author="Doc Reconstructor · Exact Mode",
    )
    doc.build(story, onFirstPage=_draw_bg, onLaterPages=_draw_bg)
    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════════════════════
# PDF 2 — ENHANCED  (same words, rich professional design, fills the page)
# ═══════════════════════════════════════════════════════════════════════════════

C_EN_ACCENT   = colors.HexColor("#2563eb")
C_EN_H1       = colors.white
C_EN_H2       = colors.HexColor("#1e3a5f")
C_EN_BODY     = colors.HexColor("#1e293b")
C_EN_KEY      = colors.HexColor("#1d4ed8")
C_EN_VAL      = colors.HexColor("#374151")
C_EN_SEP      = colors.HexColor("#3b82f6")
C_EN_THBG     = colors.HexColor("#1d4ed8")
C_EN_THFG     = colors.white
C_EN_ODD      = colors.HexColor("#eff6ff")
C_EN_EVEN     = colors.HexColor("#dbeafe")
C_EN_GRID     = colors.HexColor("#93c5fd")
C_EN_BANNER   = colors.HexColor("#0f172a")
C_EN_KV_BG_K  = colors.HexColor("#eff6ff")
C_EN_KV_BG_V  = colors.HexColor("#f8fafc")
C_EN_NUM_BG   = colors.HexColor("#2563eb")
C_EN_NUM_FG   = colors.white


def enhanced_styles(s: float = 1.0, bf: float = 10.5) -> dict:
    """
    Build ParagraphStyles for the enhanced PDF.
    s  = scale factor (expands to fill page)
    bf = base font size in pt (scales with page width)
    """
    return {
        "h1": ParagraphStyle(
            "NH1",
            fontName="Helvetica-Bold",
            fontSize=round(bf * 2.0 * s, 1),
            leading=round(bf * 2.6 * s, 1),
            textColor=C_EN_H1,
            spaceBefore=0,
            spaceAfter=round(4 * s, 1),
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "NH2",
            fontName="Helvetica-Bold",
            fontSize=round(bf * 1.25 * s, 1),
            leading=round(bf * 1.65 * s, 1),
            textColor=C_EN_H2,
            spaceBefore=round(10 * s, 1),
            spaceAfter=round(4 * s, 1),
        ),
        "para": ParagraphStyle(
            "NP",
            fontName="Helvetica",
            fontSize=round(bf * s, 1),
            leading=round(bf * 1.55 * s, 1),
            textColor=C_EN_BODY,
            spaceBefore=round(4 * s, 1),
            spaceAfter=round(4 * s, 1),
        ),
        "key": ParagraphStyle(
            "NK",
            fontName="Helvetica-Bold",
            fontSize=round(bf * 0.95 * s, 1),
            leading=round(bf * 1.35 * s, 1),
            textColor=C_EN_KEY,
        ),
        "val": ParagraphStyle(
            "NV",
            fontName="Helvetica",
            fontSize=round(bf * 0.95 * s, 1),
            leading=round(bf * 1.35 * s, 1),
            textColor=C_EN_VAL,
        ),
        "th": ParagraphStyle(
            "NTH",
            fontName="Helvetica-Bold",
            fontSize=round(9 * s, 1),
            leading=round(12 * s, 1),
            textColor=C_EN_THFG,
        ),
        "tc": ParagraphStyle(
            "NTC",
            fontName="Helvetica",
            fontSize=round(9 * s, 1),
            leading=round(12 * s, 1),
            textColor=C_EN_BODY,
        ),
        "num": ParagraphStyle(
            "NNUM",
            fontName="Helvetica-Bold",
            fontSize=round(bf * 0.9 * s, 1),
            leading=round(bf * 1.3 * s, 1),
            textColor=C_EN_NUM_FG,
            alignment=TA_CENTER,
        ),
    }


def _draw_enhanced_page(c: rl_canvas.Canvas, doc, page_size: tuple):
    """Draw the full-bleed branded header banner and footer on every page."""
    pw, ph   = page_size
    banner_h = 62
    footer_h = 30
    accent_w = 8

    # Dark navy header banner
    c.setFillColor(C_EN_BANNER)
    c.rect(0, ph - banner_h, pw, banner_h, stroke=0, fill=1)

    # Blue left-side accent stripe in header
    c.setFillColor(C_EN_ACCENT)
    c.rect(0, ph - banner_h, accent_w, banner_h, stroke=0, fill=1)

    # Decorative circles (top-right)
    c.setFillColor(colors.HexColor("#1e3a5f"))
    c.circle(pw - 40, ph - 30, 28, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#172554"))
    c.circle(pw - 18, ph - 56, 18, stroke=0, fill=1)

    # Thin accent underline below banner
    c.setStrokeColor(C_EN_ACCENT)
    c.setLineWidth(2)
    c.line(0, ph - banner_h, pw, ph - banner_h)

    # Footer bar
    c.setFillColor(C_EN_BANNER)
    c.rect(0, 0, pw, footer_h, stroke=0, fill=1)
    c.setFillColor(C_EN_ACCENT)
    c.rect(0, 0, accent_w, footer_h, stroke=0, fill=1)
    c.setStrokeColor(C_EN_ACCENT)
    c.setLineWidth(1)
    c.line(0, footer_h, pw, footer_h)

    # Footer text
    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 7.5)
    c.drawString(20, 10, "AI Document Reconstructor · Powered by Gemini 2.5 Flash")
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(pw - 20, 10, f"Page {doc.page}")


def build_enhanced_pdf(elements: list, doc_title: str, page_size: tuple) -> bytes:
    """
    Build the Enhanced PDF.
    Features: dark banner header, blue accents, numbered pills,
    styled KV pairs, subheading label boxes. Zero extra words.
    Content scales to fill the chosen page size.
    """
    pw, ph     = page_size
    margin_lr  = max(45, pw * 0.07)
    margin_top = 72        # clearance below 62pt banner + 10pt gap
    margin_bot = 40        # clearance above footer
    usable_w   = pw - 2 * margin_lr
    usable_h   = ph - margin_top - margin_bot

    # Base font scales with page width (A4 ref ~482pt → 10.5pt)
    base_font = max(9.0, min(14.0, usable_w / 48.0))

    est_h = estimate_story_height(elements, usable_w)
    scale = compute_fill_scale(est_h, usable_h * 0.92)
    sty   = enhanced_styles(scale, base_font)

    def sp(n: float) -> Spacer:
        return Spacer(1, max(2, round(n * scale, 1)))

    def accent_rule(w="100%", thick=2.5, col=C_EN_ACCENT) -> HRFlowable:
        return HRFlowable(
            width=w, thickness=thick, color=col,
            spaceBefore=round(3 * scale, 1),
            spaceAfter=round(8 * scale, 1),
        )

    # Resolve cover title
    cover_title = doc_title.strip()
    if not cover_title:
        cover_title = next(
            (e.get("text", "") for e in elements if e.get("type") == "heading"),
            "Document",
        )
    seen_cover = cover_title.strip().lower()

    story = []

    # Title block (displayed in white area below the dark banner)
    story.append(sp(4))
    story.append(Paragraph(
        f'<font color="white"><b>{cover_title}</b></font>', sty["h1"]
    ))
    story.append(sp(6))
    story.append(accent_rule("100%", 3, C_EN_ACCENT))

    # Render elements
    for elem in elements:
        t = elem.get("type", "").lower()

        # ── HEADING ──────────────────────────────────────────────────────────
        if t == "heading":
            text = str(elem.get("text", "")).strip()
            if not text or text.strip().lower() == seen_cover:
                continue
            lv = elem.get("level", 1)
            story.append(sp(6))
            if lv == 1:
                story.append(Paragraph(
                    f'<font color="#1d4ed8"><b>{text}</b></font>', sty["h1"]
                ))
                story.append(accent_rule("60%", 2.5, C_EN_ACCENT))
            else:
                story.append(Paragraph(text, sty["h2"]))
                story.append(accent_rule("30%", 1.5, C_EN_SEP))

        # ── SUBHEADING ────────────────────────────────────────────────────────
        elif t == "subheading":
            text = str(elem.get("text", "")).strip()
            if text:
                story.append(sp(6))
                sub_tbl = Table(
                    [[Paragraph(f'<b>{text}</b>', sty["h2"])]],
                    colWidths=[usable_w],
                )
                sub_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                    ("TOPPADDING",    (0, 0), (-1, -1), round(5 * scale, 1)),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), round(5 * scale, 1)),
                    ("LINEBEFORE",    (0, 0), (0, -1),  4, C_EN_ACCENT),
                    ("LINEBELOW",     (0, 0), (-1, -1), 0.5, colors.HexColor("#dbeafe")),
                ]))
                story.append(sub_tbl)
                story.append(sp(4))

        # ── PARAGRAPH ────────────────────────────────────────────────────────
        elif t == "paragraph":
            text = str(elem.get("text", "")).strip()
            if not text:
                continue
            # Detect numbered items "1. ..." or "1) ..."
            num_match = re.match(r'^([\d]+[.)]\s+)(.*)', text)
            if num_match:
                num_part  = num_match.group(1).strip()
                rest_part = num_match.group(2).strip()
                num_w     = round(base_font * 2.8 * scale, 1)
                text_w    = usable_w - num_w - 6
                num_cell  = Paragraph(f'<b>{num_part}</b>', sty["num"])
                text_cell = Paragraph(rest_part, sty["para"])
                row_tbl   = Table(
                    [[num_cell, text_cell]],
                    colWidths=[num_w, text_w],
                )
                row_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (0, 0),   C_EN_NUM_BG),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING",   (0, 0), (0, 0),   4),
                    ("RIGHTPADDING",  (0, 0), (0, 0),   4),
                    ("TOPPADDING",    (0, 0), (-1, -1), round(5 * scale, 1)),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), round(5 * scale, 1)),
                    ("LEFTPADDING",   (1, 0), (1, 0),   8),
                    ("RIGHTPADDING",  (1, 0), (1, 0),   0),
                ]))
                story.append(row_tbl)
                story.append(sp(3))
            else:
                story.append(Paragraph(text, sty["para"]))
                story.append(sp(2))

        # ── SEPARATOR ─────────────────────────────────────────────────────────
        elif t == "separator":
            story.append(sp(6))
            story.append(HRFlowable(
                width="100%", thickness=1, color=C_EN_SEP,
                spaceBefore=round(2 * scale, 1),
                spaceAfter=round(10 * scale, 1),
            ))

        # ── KEY-VALUE PAIR ────────────────────────────────────────────────────
        elif t == "key_value_pair":
            key = str(elem.get("key",   "")).strip()
            val = str(elem.get("value", "")).strip()
            if not key:
                continue
            kw = round(usable_w * 0.35, 1)
            vw = round(usable_w - kw, 1)
            kv = Table(
                [[Paragraph(f'<b>{key}</b>', sty["key"]),
                  Paragraph(val, sty["val"])]],
                colWidths=[kw, vw],
            )
            kv.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (0, 0),  C_EN_KV_BG_K),
                ("BACKGROUND",    (1, 0), (1, 0),  C_EN_KV_BG_V),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                ("TOPPADDING",    (0, 0), (-1, -1), round(5 * scale, 1)),
                ("BOTTOMPADDING", (0, 0), (-1, -1), round(5 * scale, 1)),
                ("LINEBEFORE",    (0, 0), (0, -1),  3.5, C_EN_KEY),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.4, colors.HexColor("#dbeafe")),
            ]))
            story.append(kv)
            story.append(sp(2))

        # ── TABLE ─────────────────────────────────────────────────────────────
        elif t == "table":
            story.append(sp(8))
            story.append(build_table(
                elem, sty["th"], sty["tc"],
                C_EN_THBG, C_EN_THFG, C_EN_ODD, C_EN_EVEN, C_EN_GRID,
                usable_w,
                row_pad=round(6 * scale, 1),
                font_size=round(9 * scale, 1),
            ))
            story.append(sp(8))

        else:
            text = str(elem.get("text", elem.get("content", ""))).strip()
            if text:
                story.append(Paragraph(text, sty["para"]))

    # Build PDF
    buf = io.BytesIO()
    _ps = page_size

    def _first(c, doc):
        _draw_enhanced_page(c, doc, _ps)

    def _later(c, doc):
        _draw_enhanced_page(c, doc, _ps)

    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        topMargin=margin_top,
        bottomMargin=margin_bot,
        leftMargin=margin_lr,
        rightMargin=margin_lr,
        title=cover_title,
        author="Doc Reconstructor · Enhanced Mode",
    )
    doc.build(story, onFirstPage=_first, onLaterPages=_later)
    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN UI — HEADER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <div style='text-align:left; padding-bottom:0.5rem;'>
        <h1 style='color:#f1f5f9; font-size:1.9rem; font-weight:700;
                   margin-bottom:0.2rem; letter-spacing:-0.02em;'>
            📄 AI Document &amp; Layout Reconstructor
        </h1>
        <p style='color:#64748b; font-size:0.9rem; margin:0;'>
            Upload any document photo → AI analyzes → download
            <strong style='color:#94a3b8;'>TWO PDFs</strong>:
            exact replica (notebook style) + richly designed version
            (same words, stunning visuals, page-filling layout)
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT — TWO COLUMNS
# ═══════════════════════════════════════════════════════════════════════════════

col_upload, col_result = st.columns([1, 1.4], gap="large")

with col_upload:
    st.markdown(
        "<h3 style='color:#e2e8f0; font-size:1rem; font-weight:600; "
        "margin-bottom:0.75rem;'>① Upload Source Image</h3>",
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "Drop image here or click to browse",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed",
    )

    if uploaded_file:
        img  = Image.open(uploaded_file)
        w, h = img.size
        st.image(img, caption=f"{uploaded_file.name}  ·  {w}×{h}px",
                 use_container_width=True)
        st.markdown(
            f"<div style='margin-top:0.75rem;'>"
            f"<span class='stat-badge'>📁 <span>{uploaded_file.name}</span></span>"
            f"<span class='stat-badge'>⚖️ <span>{uploaded_file.size // 1024} KB</span></span>"
            f"<span class='stat-badge'>📐 <span>{w}×{h}px</span></span>"
            f"<span class='stat-badge'>📄 <span>{page_size_label.split('(')[0].strip()}</span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class='doc-card' style='text-align:center; padding:3rem 1.5rem;'>
                <div style='font-size:3rem; margin-bottom:1rem;'>🖼️</div>
                <h3 style='font-size:0.95rem;'>No image uploaded yet</h3>
                <p>Drag &amp; drop a screenshot, photo, agenda, form,<br>
                   table, or any document image above.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


with col_result:
    st.markdown(
        "<h3 style='color:#e2e8f0; font-size:1rem; font-weight:600; "
        "margin-bottom:0.75rem;'>② Analyze &amp; Generate Two PDFs</h3>",
        unsafe_allow_html=True,
    )

    if not api_key:
        st.markdown(
            "<div class='doc-card'><h3>🔑 API Key Required</h3>"
            "<p>Enter your Google AI Studio API key in the left sidebar.</p></div>",
            unsafe_allow_html=True,
        )
    elif not uploaded_file:
        st.markdown(
            "<div class='doc-card'><h3>🖼️ Upload an Image First</h3>"
            "<p>Upload a PNG or JPG on the left, then click Analyze below.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        run_btn = st.button(
            "⚡ Analyze & Generate Both PDFs",
            use_container_width=True,
        )

        if run_btn:
            fname     = uploaded_file.name.lower()
            mime_type = "image/png" if fname.endswith(".png") else "image/jpeg"
            uploaded_file.seek(0)
            image_bytes = uploaded_file.read()

            # Step 1: Exact analysis
            with st.spinner("🖨️  Analyzing image for exact replica..."):
                try:
                    ex_elems, ex_raw = analyze_image(
                        api_key, image_bytes, mime_type, PROMPT_EXACT
                    )
                    st.session_state.update(ex_elems=ex_elems, ex_raw=ex_raw, ex_ok=True)
                except Exception as e:
                    st.error(f"❌ Exact analysis failed: {e}")
                    st.session_state["ex_ok"] = False

            # Step 2: Enhanced analysis
            with st.spinner("✨  Analyzing image for enhanced design..."):
                try:
                    en_elems, en_raw = analyze_image(
                        api_key, image_bytes, mime_type, PROMPT_ENHANCED
                    )
                    st.session_state.update(en_elems=en_elems, en_raw=en_raw, en_ok=True)
                except Exception as e:
                    st.error(f"❌ Enhanced analysis failed: {e}")
                    st.session_state["en_ok"] = False

            # Step 3: Build exact PDF
            if st.session_state.get("ex_ok"):
                with st.spinner("📄  Building exact replica PDF..."):
                    try:
                        ex_pdf = build_exact_pdf(
                            st.session_state["ex_elems"],
                            pdf_title.strip(),
                            chosen_page_size,
                        )
                        st.session_state.update(ex_pdf=ex_pdf, ex_ready=True)
                    except Exception as e:
                        st.error(f"❌ Exact PDF error: {e}")
                        st.session_state["ex_ready"] = False
                        with st.expander("Trace"):
                            st.code(traceback.format_exc())

            # Step 4: Build enhanced PDF
            if st.session_state.get("en_ok"):
                with st.spinner("✨  Building enhanced PDF..."):
                    try:
                        en_pdf = build_enhanced_pdf(
                            st.session_state["en_elems"],
                            pdf_title.strip(),
                            chosen_page_size,
                        )
                        st.session_state.update(en_pdf=en_pdf, en_ready=True)
                    except Exception as e:
                        st.error(f"❌ Enhanced PDF error: {e}")
                        st.session_state["en_ready"] = False
                        with st.expander("Trace"):
                            st.code(traceback.format_exc())

        # Results panel
        ex_ready = st.session_state.get("ex_ready")
        en_ready = st.session_state.get("en_ready")

        if ex_ready or en_ready:
            st.success("✅ Both PDFs ready for download!")
            safe_base = re.sub(r'[^\w\-_.]', '_', pdf_title.strip() or "document")

            # Exact PDF card
            if ex_ready:
                st.markdown(
                    "<div class='pdf-card-exact'>"
                    "<h3 style='color:#cbd5e1; margin:0 0 0.3rem;'>"
                    "🖨️ PDF 1 — Exact Replica</h3>"
                    "<p style='color:#64748b; font-size:0.82rem; margin:0;'>"
                    "Notebook-style paper · ruled lines · red margin line · "
                    "bordered title box · Courier body text</p></div>",
                    unsafe_allow_html=True,
                )
                ex_elems = st.session_state.get("ex_elems", [])
                tc = {}
                for e in ex_elems:
                    k = e.get("type", "?")
                    tc[k] = tc.get(k, 0) + 1
                st.markdown(
                    "<div style='margin-bottom:0.6rem;'>"
                    + "".join(
                        f"<span class='stat-badge'>{k}: <span>{v}</span></span>"
                        for k, v in tc.items()
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "⬇️ Download Exact Replica PDF",
                    data=st.session_state["ex_pdf"],
                    file_name=f"{safe_base}_exact_replica.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_exact",
                )

            st.markdown("<br>", unsafe_allow_html=True)

            # Enhanced PDF card
            if en_ready:
                st.markdown(
                    "<div class='pdf-card-enhanced'>"
                    "<h3 style='color:#6ee7b7; margin:0 0 0.3rem;'>"
                    "✨ PDF 2 — Enhanced Design</h3>"
                    "<p style='color:#4ade80; font-size:0.82rem; margin:0; opacity:0.85;'>"
                    "Same words only · rich colors · icons · bold typography · "
                    "dark banner · page-filling layout</p></div>",
                    unsafe_allow_html=True,
                )
                en_elems = st.session_state.get("en_elems", [])
                tc2 = {}
                for e in en_elems:
                    k = e.get("type", "?")
                    tc2[k] = tc2.get(k, 0) + 1
                st.markdown(
                    "<div style='margin-bottom:0.6rem;'>"
                    + "".join(
                        f"<span class='stat-badge'>{k}: <span>{v}</span></span>"
                        for k, v in tc2.items()
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "⬇️ Download Enhanced PDF",
                    data=st.session_state["en_pdf"],
                    file_name=f"{safe_base}_enhanced.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_enhanced",
                )

            # Debug expanders
            st.markdown("---")
            with st.expander(
                f"🔍 Exact elements ({len(st.session_state.get('ex_elems', []))})",
                expanded=False,
            ):
                st.json(st.session_state.get("ex_elems", []))

            with st.expander(
                f"✨ Enhanced elements ({len(st.session_state.get('en_elems', []))})",
                expanded=False,
            ):
                st.json(st.session_state.get("en_elems", []))

            with st.expander("📡 Raw Gemini responses (debug)", expanded=False):
                er = st.session_state.get("ex_raw", "")
                st.markdown("**Exact:**")
                st.code(er[:2000] + ("…" if len(er) > 2000 else ""), language="json")
                nr = st.session_state.get("en_raw", "")
                st.markdown("**Enhanced:**")
                st.code(nr[:2000] + ("…" if len(nr) > 2000 else ""), language="json")

        elif not run_btn:
            st.markdown(
                """
                <div class='doc-card'>
                    <h3>🚀 Ready to Generate Both PDFs</h3>
                    <p>Click <strong>Analyze &amp; Generate Both PDFs</strong> to begin.
                       The engine will:</p>
                    <ol style='color:#64748b; font-size:0.85rem; margin-top:0.5rem;
                               padding-left:1.2rem; line-height:2.2;'>
                        <li>Gemini Vision extracts the exact layout (verbatim text)</li>
                        <li>Gemini Vision structures it for rich design (same words, icons on keys)</li>
                        <li>Build PDF 1: cream notebook paper + blue ruled lines + red margin +
                            bordered title box + Courier typeface — visual clone of source</li>
                        <li>Build PDF 2: dark navy banner + blue accents + numbered pill items +
                            styled KV pairs — zero extra words, fills the page</li>
                    </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center; color:#334155; font-size:0.75rem;'>"
    "AI Document &amp; Layout Reconstructor · Dual PDF Engine v4 · "
    "Gemini 2.5 Flash + ReportLab · Streamlit</p>",
    unsafe_allow_html=True,
)