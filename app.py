"""
AI-Powered Document & UI Layout Reconstructor
=============================================
A Streamlit application that analyzes uploaded screenshots or photos and
reconstructs their layout as a professional, printable PDF document using
Google Gemini Vision and ReportLab.

Requirements:
    pip install streamlit google-genai reportlab Pillow
"""

import io
import json
import os
import re
import threading
import time
import traceback

import streamlit as st
import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image

# ── ReportLab imports ────────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Google GenAI import ──────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    st.error(
        "❌ `google-genai` package not found. Install it with: "
        "`pip install google-genai`"
    )
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI BRIDGE — PARALLEL REST API ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

api_bridge = FastAPI(title="Doc Reconstructor API Bridge", version="1.0.0")

api_bridge.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api_bridge.post("/reconstruct")
async def api_reconstruct_layout(file: UploadFile = File(...)):
    """
    Accepts an uploaded image (PNG or JPEG) and returns a reconstructed PDF
    as a downloadable binary response. Intended for automated external callers.
    """
    try:
        image_bytes = await file.read()

        # Determine MIME type from filename or content-type header
        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        if filename.endswith(".png") or "png" in content_type:
            mime_type = "image/png"
        else:
            mime_type = "image/jpeg"

        # Retrieve the API key from the environment (set via GOOGLE_API_KEY)
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return Response(
                content=json.dumps({"error": "GOOGLE_API_KEY environment variable is not set."}),
                media_type="application/json",
                status_code=500,
            )

        # Run core engine: Gemini Vision analysis → PDF reconstruction
        elements, _raw = analyze_image_with_gemini(
            api_key=api_key,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        pdf_bytes = reconstruct_pdf(elements=elements, doc_title="API Export")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="reconstructed.pdf"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except Exception as exc:
        error_detail = {
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        return Response(
            content=json.dumps(error_detail),
            media_type="application/json",
            status_code=500,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Doc Reconstructor · AI Layout Engine",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM CSS — PREMIUM DARK-MODE THEME
# ═══════════════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
<style>
/* ── Global Reset & Body Canvas ─────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #020617 !important;
    color: #e2e8f0 !important;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

[data-testid="stApp"] {
    background-color: #020617 !important;
}

/* ── Main Content Area ───────────────────────────────────────────────────── */
[data-testid="stMain"] {
    background-color: #020617 !important;
}

.main .block-container {
    background-color: #020617 !important;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #0f172a !important;
    border-right: 1px solid #1e293b;
}

[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}

[data-testid="stSidebar"] .stTextInput > div > div > input {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
    border-radius: 8px;
}

[data-testid="stSidebar"] .stTextInput > div > div > input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25) !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #f1f5f9 !important;
}

/* ── File Uploader ───────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background-color: #0f172a !important;
    border: 2px dashed #334155 !important;
    border-radius: 12px !important;
    padding: 1rem;
    transition: border-color 0.2s ease;
}

[data-testid="stFileUploader"]:hover {
    border-color: #3b82f6 !important;
}

[data-testid="stFileUploader"] * {
    color: #94a3b8 !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8, #2563eb) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35) !important;
    width: 100%;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #1e40af, #1d4ed8) !important;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.5) !important;
    transform: translateY(-1px) !important;
}

.stButton > button:active {
    transform: translateY(0px) !important;
}

/* ── Download Button ─────────────────────────────────────────────────────── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #047857, #059669) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 12px rgba(5, 150, 105, 0.35) !important;
    width: 100%;
}

.stDownloadButton > button:hover {
    background: linear-gradient(135deg, #065f46, #047857) !important;
    box-shadow: 0 6px 18px rgba(5, 150, 105, 0.5) !important;
    transform: translateY(-1px) !important;
}

/* ── Alerts & Info Boxes ─────────────────────────────────────────────────── */
.stAlert {
    border-radius: 10px !important;
    border: none !important;
}

[data-testid="stInfoBox"] {
    background-color: #0c1a2e !important;
    border-left: 4px solid #3b82f6 !important;
    border-radius: 8px !important;
    color: #93c5fd !important;
}

[data-testid="stSuccessBox"] {
    background-color: #052e16 !important;
    border-left: 4px solid #22c55e !important;
    border-radius: 8px !important;
}

[data-testid="stErrorBox"] {
    background-color: #2d0a0a !important;
    border-left: 4px solid #ef4444 !important;
    border-radius: 8px !important;
}

[data-testid="stWarningBox"] {
    background-color: #1c1400 !important;
    border-left: 4px solid #f59e0b !important;
    border-radius: 8px !important;
}

/* ── Spinner ─────────────────────────────────────────────────────────────── */
.stSpinner > div {
    border-top-color: #3b82f6 !important;
}

/* ── Expander ────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background-color: #0f172a !important;
    border: 1px solid #1e293b !important;
    border-radius: 10px !important;
}

[data-testid="stExpander"] summary {
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}

/* ── Images ──────────────────────────────────────────────────────────────── */
[data-testid="stImage"] img {
    border-radius: 10px !important;
    border: 1px solid #1e293b !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0f172a; }
::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #475569; }

/* ── Custom Card ─────────────────────────────────────────────────────────── */
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

.doc-card p {
    color: #64748b;
    margin: 0;
    font-size: 0.875rem;
    line-height: 1.6;
}

/* ── Badge / Stat ────────────────────────────────────────────────────────── */
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

.stat-badge span {
    color: #3b82f6;
    font-weight: 700;
}

/* ── Divider ─────────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid #1e293b !important;
    margin: 1.5rem 0 !important;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — API KEY & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📄 Doc Reconstructor")
    st.markdown(
        "<p style='color:#64748b; font-size:0.82rem; margin-top:-0.5rem;'>"
        "AI-Powered Layout Engine · v1.0</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### 🔑 API Configuration")
    api_key = st.text_input(
        "Google AI Studio API Key",
        type="password",
        placeholder="AIza...",
        help="Get your free key at https://aistudio.google.com/",
    )

    if not api_key:
        st.info(
            "🔐 **API Key Required**\n\n"
            "Enter your Google AI Studio API key above to enable the "
            "Gemini Vision analysis engine.\n\n"
            "👉 [Get a free key →](https://aistudio.google.com/)"
        )

    st.markdown("---")
    st.markdown("### ⚙️ PDF Settings")

    pdf_title = st.text_input(
        "Document Title (optional)",
        placeholder="Reconstructed Document",
        value="",
    )


    st.markdown("---")
    st.markdown("### 📋 Supported Element Types")

    element_types = [
        ("H1/H2", "Headings & Subheadings"),
        ("¶", "Paragraphs"),
        ("━━", "Separators"),
        ("Key: Val", "Key-Value Pairs"),
        ("▦", "Tables (with zebra rows)"),
    ]

    for badge, label in element_types:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:0.6rem; "
            f"margin-bottom:0.4rem;'>"
            f"<span style='background:#1e293b; border:1px solid #334155; "
            f"color:#3b82f6; border-radius:4px; padding:2px 8px; "
            f"font-size:0.72rem; font-family:monospace;'>{badge}</span>"
            f"<span style='color:#94a3b8; font-size:0.82rem;'>{label}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        "<p style='color:#334155; font-size:0.72rem; text-align:center;'>"
        "Powered by Gemini 2.5 Flash · ReportLab</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: EXPONENTIAL BACKOFF RETRY WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

def generate_content_with_retry(client, model: str, contents, max_retries: int = 5):
    """
    Calls the Gemini API with exponential backoff to handle transient
    503 UNAVAILABLE errors during high-demand spikes.

    Retry delays: 1s → 2s → 4s → 8s → 16s
    Raises the final exception if all retries are exhausted.
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            return response

        except Exception as exc:
            last_exception = exc
            error_str = str(exc).lower()

            # Only retry on transient server-side errors
            is_transient = any(
                code in error_str
                for code in ["503", "unavailable", "resource exhausted", "429", "500"]
            )

            if not is_transient:
                # Non-transient error → raise immediately
                raise exc

            wait_seconds = 2 ** attempt  # 1, 2, 4, 8, 16
            if attempt < max_retries - 1:
                st.toast(
                    f"⚠️ API busy — retrying in {wait_seconds}s "
                    f"(attempt {attempt + 1}/{max_retries})",
                    icon="🔄",
                )
                time.sleep(wait_seconds)

    # All retries exhausted
    raise last_exception


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: ROBUST MULTI-STAGE JSON PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def extract_document_elements_safely(raw_text: str) -> list:
    """
    Multi-stage JSON parser with progressive fallback strategies:
      Stage 1 → Standard json.loads()
      Stage 2 → Regex extraction between outermost [ ... ]
      Stage 3 → Strip markdown fences (```json, ```python, ```) and retry
      Raises ValueError with a clear message if all stages fail.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response received from the AI model.")

    text = raw_text.strip()

    # ── Stage 1: Direct JSON parse ───────────────────────────────────────────
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        # If root is a dict with a key containing a list, unwrap it
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # ── Stage 2: Regex extraction between outermost square brackets ──────────
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            extracted = match.group(0)
            parsed = json.loads(extracted)
            if isinstance(parsed, list):
                return parsed
    except (json.JSONDecodeError, AttributeError):
        pass

    # ── Stage 3: Strip markdown fences and retry ─────────────────────────────
    try:
        # Remove ```json, ```python, ``` fences
        cleaned = re.sub(r'```(?:json|python|javascript)?\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()

        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed

        # Try regex on the cleaned version too
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
    except (json.JSONDecodeError, AttributeError):
        pass

    # ── All stages failed ────────────────────────────────────────────────────
    raise ValueError(
        f"JSON parsing failed after 3 stages. "
        f"Raw response preview: {raw_text[:300]}..."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: GEMINI VISION — ANALYZE IMAGE INTO STRUCTURED JSON
# ═══════════════════════════════════════════════════════════════════════════════

VISION_PROMPT = (
    "You are an elite Document Layout Specialist. Reconstruct the COMPLETE visual "
    "content of the provided image into a structured JSON array for PDF printing.\n\n"
    "Your goal: the PDF must look like a faithful text/table representation of the "
    "image — including header stats, filter chips, the full data table, and the "
    "footer toggle labels. Nothing should be skipped.\n\n"
    "=== ELEMENT TYPES — use exactly these ===\n\n"
    "1. HEADING (page title + inline stats combined into one string):\n"
    '   { "type": "heading", "text": "Sessions \u00b7 8   \u2705 65.6%", "level": 1 }\n'
    "   Combine the title, count bullet, and any badge/percentage into ONE heading string.\n\n"
    "2. TOOLBAR (the row of filter chip buttons below the title):\n"
    '   { "type": "toolbar", "items": ["Period", "Courses (2)", "Activities (1)", "Search", "More"] }\n'
    "   List every visible chip/button label. Exclude the toggle switch icon itself.\n\n"
    "3. TABLE (the main data grid):\n"
    '   { "type": "table", "headers": ["Date","Time","Duration","Course","Activity","Note"], '
    '"rows": [["15/05/26","23:39 \u2013 23:39","\u2013","Maths","","kvnrogbv n;3ojb fvo;rn gvo;3rng..."], ...] }\n'
    "   Rules:\n"
    "   - Headers: ONLY the semantic data columns shown in the column header row.\n"
    "     Do NOT include a checkbox column or an actions column.\n"
    "   - Rows: capture ALL data rows top to bottom, none skipped.\n"
    "   - Each row must have the SAME number of cells as headers. Use \"\" for empty cells.\n"
    "   - Time ranges: preserve exactly as shown e.g. '23:39 \u2013 23:39'.\n"
    "   - Duration dash: use '\u2013' if shown as a dash/em-dash.\n"
    "   - Course pills: transcribe text inside the badge e.g. 'Maths', 'kvnfek', 'kjvenf'.\n"
    "   - Note text: transcribe verbatim including trailing '...' if truncated.\n"
    "   - Do NOT include the '...' action menu as a cell value.\n\n"
    "4. TOGGLE_ROW (the footer row showing toggle labels):\n"
    '   { "type": "toggle_row", "items": ["Show activities", "Show notes"] }\n'
    "   List each toggle label. Do not describe the toggle switch graphic.\n\n"
    "5. SEPARATOR:\n"
    '   { "type": "separator" }\n\n'
    "6. KEY_VALUE_PAIR (for forms):\n"
    '   { "type": "key_value_pair", "key": "Label", "value": "Value" }\n\n'
    "7. PARAGRAPH:\n"
    '   { "type": "paragraph", "text": "..." }\n\n'
    "=== OUTPUT RULES ===\n"
    "- Return ONLY a raw JSON array. No preamble, no markdown fences.\n"
    "- Start with [ and end with ].\n"
    "- JSON must be valid and parseable.\n\n"
    "=== QUALITY CHECKLIST ===\n"
    "- Heading combines title + count + badge into one string\n"
    "- Toolbar lists all filter chip labels\n"
    "- Table has correct headers (no checkbox/action cols)\n"
    "- Table has ALL data rows (count them against the image)\n"
    "- Each table row has same cell count as headers\n"
    "- Toggle footer captured as toggle_row\n"
    "- Response starts with [ and ends with ]\n\n"
    "Analyze the image now and return the JSON array:"
)


def analyze_image_with_gemini(api_key: str, image_bytes: bytes, mime_type: str) -> list:
    """
    Sends the uploaded image to Gemini 2.5 Flash for structured layout analysis.
    Returns a list of document element dicts.
    """
    client = genai.Client(api_key=api_key)

    # Build the multimodal content payload
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    text_part = genai_types.Part.from_text(text=VISION_PROMPT)

    contents = [genai_types.Content(parts=[image_part, text_part], role="user")]

    response = generate_content_with_retry(
        client=client,
        model="gemini-2.5-flash",
        contents=contents,
        max_retries=5,
    )

    raw_text = response.text
    elements = extract_document_elements_safely(raw_text)
    return elements, raw_text


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: HIGH-FIDELITY PDF BUILDER (ReportLab)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Color constants ──────────────────────────────────────────────────────────
COLOR_HEADER_BG    = colors.HexColor("#1e293b")
COLOR_HEADER_FG    = colors.white
COLOR_ROW_ODD      = colors.HexColor("#f8fafc")
COLOR_ROW_EVEN     = colors.HexColor("#f1f5f9")
COLOR_GRID         = colors.HexColor("#cbd5e1")
COLOR_SEPARATOR    = colors.HexColor("#e2e8f0")
COLOR_KEY          = colors.HexColor("#1e40af")
COLOR_H1           = colors.HexColor("#0f172a")
COLOR_H2           = colors.HexColor("#1e293b")
COLOR_BODY         = colors.HexColor("#1e293b")


def build_pdf_style_catalog() -> dict:
    """
    Creates and returns a dictionary of ParagraphStyle objects for the PDF.
    All styles use Helvetica (no external fonts required).
    """
    base = getSampleStyleSheet()

    styles = {
        "h1": ParagraphStyle(
            "DocH1",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=COLOR_H1,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "DocH2",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=COLOR_H2,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "paragraph": ParagraphStyle(
            "DocPara",
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=COLOR_BODY,
            spaceBefore=4,
            spaceAfter=4,
        ),
        "key": ParagraphStyle(
            "DocKey",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=COLOR_KEY,
            spaceBefore=2,
            spaceAfter=0,
        ),
        "value": ParagraphStyle(
            "DocValue",
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=COLOR_BODY,
            spaceBefore=0,
            spaceAfter=6,
        ),
        "table_header": ParagraphStyle(
            "DocTableHeader",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=COLOR_HEADER_FG,
        ),
        "table_cell": ParagraphStyle(
            "DocTableCell",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=COLOR_BODY,
        ),
        "meta": ParagraphStyle(
            "DocMeta",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#94a3b8"),
            spaceBefore=2,
            spaceAfter=2,
        ),
        # ── Toolbar chip label style ──────────────────────────────────────────
        "chip": ParagraphStyle(
            "DocChip",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1e40af"),
        ),
        # ── Toggle label style ────────────────────────────────────────────────
        "toggle_label": ParagraphStyle(
            "DocToggle",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
        ),
    }

    return styles


def compute_column_widths(num_cols: int, page_width: float = 520) -> list:
    """
    Returns column widths (in points) for a table fitted to the printable page.
    Presets cover the most common column counts; all sums equal page_width (520pt).
    """
    presets = {
        1: [520],
        2: [200, 320],
        3: [120, 180, 220],
        4: [95,  120, 120, 185],
        5: [80,  100,  80,  100, 160],
        6: [65,   95,   55,   65,  75, 165],
        7: [60,   90,   55,   60,  70, 130,  55],
        8: [55,   80,   50,   60,  65, 100,  60,  50],
    }
    if num_cols in presets:
        widths = list(presets[num_cols])
        drift = page_width - sum(widths)
        if drift != 0:
            widths[-1] = round(widths[-1] + drift, 2)
        return widths
    col_w = page_width / num_cols
    widths = [round(col_w, 2)] * num_cols
    drift = page_width - sum(widths)
    widths[-1] = round(widths[-1] + drift, 2)
    return widths


def build_table_flowable(element: dict, styles: dict) -> Table:
    """
    Constructs a ReportLab Table flowable from a 'table' type element.
    Applies header styling, alternating zebra rows, cell padding, and gridlines.
    """
    raw_headers = element.get("headers", [])
    raw_rows    = element.get("rows", [])

    if not raw_headers:
        raw_headers = ["Column"]

    num_cols = len(raw_headers)

    # ── Build header row (Paragraph cells for auto-wrapping) ────────────────
    header_cells = [
        Paragraph(str(h), styles["table_header"]) for h in raw_headers
    ]

    # ── Build data rows (ensure consistent column count) ────────────────────
    data_rows = []
    for row in raw_rows:
        # Pad or trim to match header column count
        padded = list(row) + [""] * max(0, num_cols - len(row))
        padded = padded[:num_cols]
        data_rows.append(
            [Paragraph(str(cell), styles["table_cell"]) for cell in padded]
        )

    # ── Combine header + data ────────────────────────────────────────────────
    table_data = [header_cells] + data_rows

    col_widths = compute_column_widths(num_cols)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    # ── Build TableStyle with zebra striping ─────────────────────────────────
    ts_commands = [
        # Header background & text
        ("BACKGROUND",  (0, 0), (-1, 0),  COLOR_HEADER_BG),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  COLOR_HEADER_FG),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("TOPPADDING",  (0, 0), (-1, 0),  7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        # Data row styling
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TOPPADDING",  (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        # Gridlines
        ("GRID",        (0, 0), (-1, -1), 0.5, COLOR_GRID),
        ("LINEBELOW",   (0, 0), (-1, 0),  1.0, COLOR_HEADER_BG),
    ]

    # Alternating zebra rows (odd = lighter, even = slightly darker)
    for row_idx in range(1, len(table_data)):
        bg = COLOR_ROW_ODD if row_idx % 2 == 1 else COLOR_ROW_EVEN
        ts_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg))
        ts_commands.append(("TEXTCOLOR",  (0, row_idx), (-1, row_idx), COLOR_BODY))

    tbl.setStyle(TableStyle(ts_commands))
    return tbl


def reconstruct_pdf(
    elements: list,
    doc_title: str = "",
) -> bytes:
    """
    Converts the list of structured document elements into a professional
    PDF using ReportLab flowables. Returns the PDF as raw bytes.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=45,
        bottomMargin=45,
        leftMargin=45,
        rightMargin=45,
        title=doc_title or "Reconstructed Document",
        author="Doc Reconstructor · AI Layout Engine",
    )

    styles  = build_pdf_style_catalog()
    story   = []

    # ── Document Title (only if user explicitly provided one) ───────────────
    if doc_title:
        story.append(Paragraph(doc_title, styles["h1"]))
        story.append(
            HRFlowable(
                width="100%",
                thickness=2,
                color=COLOR_SEPARATOR,
                spaceAfter=10,
            )
        )
        story.append(Spacer(1, 6))

    # ── Process each element ─────────────────────────────────────────────────
    for elem in elements:
        elem_type = elem.get("type", "").lower()

        if elem_type == "heading":
            text  = str(elem.get("text", "")).strip()
            level = elem.get("level", 1)
            sty   = styles["h1"] if level == 1 else styles["h2"]
            if text:
                story.append(Spacer(1, 4))
                story.append(Paragraph(text, sty))

        elif elem_type == "subheading":
            text = str(elem.get("text", "")).strip()
            if text:
                story.append(Spacer(1, 4))
                story.append(Paragraph(text, styles["h2"]))

        elif elem_type == "paragraph":
            text = str(elem.get("text", "")).strip()
            if text:
                story.append(Paragraph(text, styles["paragraph"]))

        elif elem_type == "separator":
            story.append(Spacer(1, 6))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.8,
                    color=COLOR_SEPARATOR,
                    spaceBefore=4,
                    spaceAfter=8,
                )
            )

        elif elem_type == "key_value_pair":
            key   = str(elem.get("key",   "")).strip()
            value = str(elem.get("value", "")).strip()
            if key or value:
                if key:
                    story.append(Paragraph(key, styles["key"]))
                if value:
                    story.append(Paragraph(value, styles["value"]))
                else:
                    story.append(Spacer(1, 4))

        elif elem_type == "table":
            tbl = build_table_flowable(elem, styles)
            story.append(Spacer(1, 8))
            story.append(tbl)
            story.append(Spacer(1, 8))

        elif elem_type == "toolbar":
            # Render filter chips as a single row table with pill-like cells
            items = elem.get("items", [])
            if items:
                story.append(Spacer(1, 6))
                chip_cells = []
                for item in items:
                    chip_cells.append(Paragraph(str(item), styles["chip"]))
                # Single-row table, evenly distribute width
                n = len(chip_cells)
                chip_w = round(520 / n, 1)
                chip_widths = [chip_w] * n
                chip_widths[-1] = round(520 - chip_w * (n - 1), 1)
                tbl = Table([chip_cells], colWidths=chip_widths)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
                    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica"),
                    ("FONTSIZE",      (0, 0), (-1, 0), 9),
                    ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
                    ("VALIGN",        (0, 0), (-1, 0), "MIDDLE"),
                    ("TOPPADDING",    (0, 0), (-1, 0), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                    ("LEFTPADDING",   (0, 0), (-1, 0), 6),
                    ("RIGHTPADDING",  (0, 0), (-1, 0), 6),
                    ("ROUNDEDCORNERS",(0, 0), (-1, 0), [4, 4, 4, 4]),
                    ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                    ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.HexColor("#dbeafe")),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 8))

        elif elem_type == "toggle_row":
            # Render toggle labels as: [ON] Label   [ON] Label
            items = elem.get("items", [])
            if items:
                story.append(Spacer(1, 8))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#e2e8f0"),
                        spaceBefore=2,
                        spaceAfter=6,
                    )
                )
                # Build each toggle as "[ON] Label" text inline
                toggle_parts = []
                for item in items:
                    toggle_parts.append(
                        Paragraph(
                            f'<font color="#22c55e"><b>[ON]</b></font>'
                            f'<font color="#475569">  {item}</font>',
                            styles["toggle_label"],
                        )
                    )
                # Lay them out side-by-side in a simple table
                n = len(toggle_parts)
                col_w = round(520 / n, 1)
                col_widths = [col_w] * n
                col_widths[-1] = round(520 - col_w * (n - 1), 1)
                toggle_tbl = Table([toggle_parts], colWidths=col_widths)
                toggle_tbl.setStyle(TableStyle([
                    ("ALIGN",         (0, 0), (-1, 0), "LEFT"),
                    ("VALIGN",        (0, 0), (-1, 0), "MIDDLE"),
                    ("TOPPADDING",    (0, 0), (-1, 0), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                    ("LEFTPADDING",   (0, 0), (-1, 0), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, 0), 0),
                ]))
                story.append(toggle_tbl)

        else:
            # Unknown element type — attempt to render as paragraph
            text = str(elem.get("text", elem.get("content", ""))).strip()
            if text:
                story.append(Paragraph(text, styles["paragraph"]))

    # ── Build PDF ────────────────────────────────────────────────────────────
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


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
            Upload any screenshot or photo → AI analyzes the layout → 
            Download a clean, professional PDF
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
        help="Supported formats: PNG, JPG, JPEG",
        label_visibility="collapsed",
    )

    if uploaded_file:
        img = Image.open(uploaded_file)
        w, h = img.size
        st.image(img, caption=f"{uploaded_file.name}  ·  {w}×{h}px", use_container_width=True)

        st.markdown(
            f"""
            <div style='margin-top:0.75rem;'>
                <span class='stat-badge'>📁 <span>{uploaded_file.name}</span></span>
                <span class='stat-badge'>⚖️ <span>{uploaded_file.size // 1024} KB</span></span>
                <span class='stat-badge'>📐 <span>{w}×{h}px</span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            """
            <div class='doc-card' style='text-align:center; padding:3rem 1.5rem;'>
                <div style='font-size:3rem; margin-bottom:1rem;'>🖼️</div>
                <h3 style='font-size:0.95rem;'>No image uploaded yet</h3>
                <p>Drag &amp; drop a screenshot, photo, form, table,<br>
                   dashboard, or any UI element above.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


with col_result:
    st.markdown(
        "<h3 style='color:#e2e8f0; font-size:1rem; font-weight:600; "
        "margin-bottom:0.75rem;'>② Analyze &amp; Generate PDF</h3>",
        unsafe_allow_html=True,
    )

    # ── Guard: API key required ──────────────────────────────────────────────
    if not api_key:
        st.markdown(
            """
            <div class='doc-card'>
                <h3>🔑 API Key Required</h3>
                <p>Please enter your Google AI Studio API key in the left 
                   sidebar to enable the Gemini Vision analysis engine.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Guard: Image required ────────────────────────────────────────────────
    elif not uploaded_file:
        st.markdown(
            """
            <div class='doc-card'>
                <h3>🖼️ Upload an Image First</h3>
                <p>Upload a PNG or JPG screenshot on the left panel, then 
                   click <strong>Analyze &amp; Reconstruct</strong> below.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        # ── Process Button ───────────────────────────────────────────────────
        run_btn = st.button(
            "⚡ Analyze & Reconstruct Layout",
            use_container_width=True,
        )

        if run_btn:
            # Determine MIME type
            fname = uploaded_file.name.lower()
            if fname.endswith(".png"):
                mime_type = "image/png"
            else:
                mime_type = "image/jpeg"

            # Read raw bytes
            uploaded_file.seek(0)
            image_bytes = uploaded_file.read()

            # ── Step 1: Gemini Vision Analysis ──────────────────────────────
            with st.spinner("🔍 Analyzing layout with Gemini Vision..."):
                try:
                    elements, raw_response = analyze_image_with_gemini(
                        api_key=api_key,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                    )
                    st.session_state["elements"]     = elements
                    st.session_state["raw_response"] = raw_response
                    st.session_state["analysis_ok"]  = True
                except Exception as exc:
                    st.error(f"❌ Gemini Vision Error: {exc}")
                    st.session_state["analysis_ok"] = False
                    if st.checkbox("Show error trace"):
                        st.code(traceback.format_exc(), language="text")

            # ── Step 2: PDF Generation ───────────────────────────────────────
            if st.session_state.get("analysis_ok"):
                with st.spinner("📄 Reconstructing PDF layout..."):
                    try:
                        final_title = pdf_title.strip()

                        pdf_bytes = reconstruct_pdf(
                            elements=st.session_state["elements"],
                            doc_title=final_title,
                        )
                        st.session_state["pdf_bytes"]   = pdf_bytes
                        st.session_state["pdf_title"]   = final_title if final_title else "document"
                        st.session_state["pdf_ready"]   = True
                    except Exception as exc:
                        st.error(f"❌ PDF Generation Error: {exc}")
                        st.session_state["pdf_ready"] = False
                        if st.checkbox("Show PDF error trace"):
                            st.code(traceback.format_exc(), language="text")

        # ── Results Panel ────────────────────────────────────────────────────
        if st.session_state.get("pdf_ready"):
            elements  = st.session_state["elements"]
            pdf_bytes = st.session_state["pdf_bytes"]
            pdf_title_display = st.session_state.get("pdf_title", "Document")

            st.success(f"✅ Layout reconstructed successfully!")

            # Stats
            elem_types = {}
            for e in elements:
                t = e.get("type", "unknown")
                elem_types[t] = elem_types.get(t, 0) + 1

            badges_html = "".join(
                f"<span class='stat-badge'>{t}: <span>{c}</span></span>"
                for t, c in elem_types.items()
            )
            st.markdown(
                f"<div style='margin-bottom:1rem;'>{badges_html}</div>",
                unsafe_allow_html=True,
            )

            # Download button
            safe_fname = re.sub(r'[^\w\-_.]', '_', pdf_title_display)
            st.download_button(
                label="⬇️ Download Reconstructed PDF",
                data=pdf_bytes,
                file_name=f"{safe_fname}_reconstructed.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            st.markdown("---")

            # Raw JSON preview (collapsible)
            with st.expander(
                f"🔍 View extracted structure ({len(elements)} elements)", expanded=False
            ):
                st.json(elements)

            # Raw AI response (collapsible)
            with st.expander("📡 Raw Gemini response (debug)", expanded=False):
                raw = st.session_state.get("raw_response", "")
                st.code(raw[:3000] + ("..." if len(raw) > 3000 else ""), language="json")

        elif not st.session_state.get("analysis_ok", True) is False:
            # Default state before first run
            if not run_btn:
                st.markdown(
                    """
                    <div class='doc-card'>
                        <h3>🚀 Ready to Reconstruct</h3>
                        <p>Click <strong>Analyze &amp; Reconstruct Layout</strong> to 
                           begin the AI-powered analysis. The engine will:</p>
                        <ol style='color:#64748b; font-size:0.85rem; margin-top:0.5rem;
                                   padding-left:1.2rem; line-height:2;'>
                            <li>Send your image to Gemini 2.5 Flash Vision</li>
                            <li>Parse the structured JSON layout output</li>
                            <li>Reconstruct a professional PDF via ReportLab</li>
                            <li>Deliver a clean, print-ready document</li>
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
    "AI Document &amp; Layout Reconstructor · Powered by Gemini 2.5 Flash + ReportLab · "
    "Built with Streamlit</p>",
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND API THREAD BOOTSTRAP
# Bootstrap the FastAPI bridge on port 8000 in a daemonized background thread.
# The _API_BRIDGE_STARTED flag prevents duplicate listener instances when
# Streamlit's hot-reload mechanism re-executes this module.
# ═══════════════════════════════════════════════════════════════════════════════

if not os.environ.get("_API_BRIDGE_STARTED"):
    os.environ["_API_BRIDGE_STARTED"] = "1"

    def _run_api_bridge():
        uvicorn.run(api_bridge, host="0.0.0.0", port=8000, log_level="warning")

    threading.Thread(target=_run_api_bridge, daemon=True).start()
