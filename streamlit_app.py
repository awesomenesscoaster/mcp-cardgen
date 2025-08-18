import io, csv, datetime, streamlit as st
from PIL import Image
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

# ---------- CONFIG ----------
ORG_NAME = "Medical Certificate Program"
CARD_W, CARD_H = 3.5 * inch, 2.25 * inch     # wallet card size
MARGIN_X, MARGIN_Y = 0.5 * inch, 0.5 * inch
COLS, ROWS = 2, 4                             # 8 cards per Letter page

# ---------- BARCODE ----------
def make_code128(data: str) -> Image.Image:
    """Generate a Code128 barcode as a PIL.Image."""
    code = Code128(str(data), writer=ImageWriter())
    fp = io.BytesIO()
    code.write(
        fp,
        options={
            "module_width": 0.22,    # bar thickness (0.20–0.26 work well)
            "module_height": 18.0,   # bar height
            "font_size": 11,         # human-readable text under bars
            "text_distance": 6,
            "quiet_zone": 2,         # extra white space on sides
        },
    )
    fp.seek(0)
    return Image.open(fp).convert("RGB")

# ---------- ID GENERATOR ----------
def next_mcp_id_func(prefix="MCP", grad_year=None, start=1, taken=None):
    """
    Yields IDs like MCP-26-0001. Grad year is typically two digits.
    'taken' is a set of already-used IDs to avoid collisions.
    """
    taken = set(taken or [])
    yy = (str(grad_year)[-2:] if grad_year else datetime.datetime.now().strftime("%y"))
    base = f"{prefix}-{yy}-"
    n = start
    while True:
        candidate = f"{base}{n:04d}"
        if candidate not in taken:
            yield candidate
        n += 1

# ---------- CARD RENDER ----------
def draw_card(c, x, y, student_id, first, last, grad_year=None, logo_bytes: bytes | None = None):
    """Draw a single card at (x,y) on the ReportLab canvas."""
    # Border
    c.roundRect(x, y, CARD_W, CARD_H, 10, stroke=1, fill=0)

    # Text block (top-left)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x + 0.20 * inch, y + CARD_H - 0.35 * inch, f"{first} {last}".strip())
    c.setFont("Helvetica", 10)
    c.drawString(x + 0.20 * inch, y + CARD_H - 0.55 * inch, f"Student ID: {student_id}")
    if grad_year:
        c.drawString(x + 0.20 * inch, y + CARD_H - 0.72 * inch, f"Grad Year: {grad_year}")
    c.setFont("Helvetica-Oblique", 9)
    c.drawRightString(x + CARD_W - 0.12 * inch, y + 0.15 * inch, ORG_NAME)

    # Code128 barcode (large, centered near bottom)
    bc_img = make_code128(student_id)
    bc_buf = io.BytesIO(); bc_img.save(bc_buf, format="PNG"); bc_buf.seek(0)

    bc_w_in = CARD_W - 0.40 * inch   # 0.20" margins on both sides
    bc_h_in = 0.80 * inch
    bc_x = x + 0.20 * inch
    bc_y = y + 0.4 * inch

    c.drawImage(
        ImageReader(bc_buf),
        bc_x,
        bc_y,
        width=bc_w_in,
        height=bc_h_in,
        preserveAspectRatio=True,
        mask='auto'
    )

    # Optional logo (top-right)
    if logo_bytes:
        lb = io.BytesIO(logo_bytes); lb.seek(0)
        c.drawImage(
            ImageReader(lb),
            x + CARD_W - 0.85 * inch,
            y + CARD_H - 0.85 * inch,
            width=0.80 * inch,
            height=0.80 * inch,
            preserveAspectRatio=True,
            mask='auto'
        )

# ---------- PDF MAKER ----------
def make_pdf(cards, logo_file=None) -> bytes:
    """
    cards: list of dicts with keys: id, first, last, grad_year (optional)
    logo_file: Streamlit UploadedFile or None
    """
    # gaps BETWEEN cards (tweak these)
    x_margin = 0.30 * inch   # horizontal spacing between columns
    y_margin = 0.20 * inch   # vertical spacing between rows

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    page_w, page_h = letter

    # Cache logo bytes once (UploadedFile is a stream)
    logo_bytes = None
    if logo_file is not None:
        logo_bytes = logo_file.read()

    i = 0
    for card in cards:
        col = i % COLS
        row = (i // COLS) % ROWS

        # Bottom-left of the card:
        #  - start at page margin (MARGIN_X / MARGIN_Y)
        #  - then add card width/height * col/row
        #  - plus spacing for each gap already passed
        x = MARGIN_X + col * (CARD_W + x_margin)
        # for Y: subtract from top; only add y_margin after the first row
        y = page_h - MARGIN_Y - (row + 1) * CARD_H - row * y_margin

        draw_card(
            c,
            x,
            y,
            card["id"],
            card["first"],
            card["last"],
            card.get("grad_year"),
            logo_bytes=logo_bytes
        )

        i += 1
        # new page after filling the grid
        if i % (COLS * ROWS) == 0:
            c.showPage()

    # flush the last partially filled page
    if i % (COLS * ROWS) != 0:
        c.showPage()

    c.save()
    return buf.getvalue()

# ---------- UI ----------
st.set_page_config(page_title="MCP Card Generator", page_icon="🪪", layout="centered")
st.title("MCP Card Generator")

tabs = st.tabs(["On-Demand", "Batch CSV"])

# ---- On-Demand ----
with tabs[0]:
    st.subheader("Generate a single card (Code128)")
    first = st.text_input("First Name")
    last = st.text_input("Last Name")
    id_mode = st.radio("Student ID", ["Type ID", "Auto-assign MCP ID"], horizontal=True)
    grad_year = st.text_input("Grad Year (optional, e.g., 2026)")
    logo = st.file_uploader("Optional logo (PNG)", type=["png"])

    if id_mode == "Type ID":
        sid = st.text_input("Student ID (required)")
    else:
        prefix = st.text_input("ID Prefix", value="MCP")
        yy = st.text_input("Two-digit year", value=datetime.datetime.now().strftime("%y"))
        seq = st.number_input("Start sequence", min_value=1, value=1, step=1)
        # In production, pass taken IDs from your master to avoid collisions
        sid = next(next_mcp_id_func(prefix, yy, seq, taken=set()))

    if st.button("Generate Card PDF", type="primary"):
        if not first or not last or not sid:
            st.error("First, Last, and Student ID are required.")
        else:
            pdf_bytes = make_pdf(
                [{"id": sid, "first": first, "last": last, "grad_year": grad_year}],
                logo_file=logo
            )
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"Card_{sid}.pdf",
                mime="application/pdf"
            )

# ---- Batch ----
with tabs[1]:
    st.subheader("Batch from CSV (Code128)")
    st.caption("CSV headers required: **Student ID, First Name, Last Name**. Optional: **Grad Year**.")
    csv_file = st.file_uploader("Upload CSV", type=["csv"])
    auto_assign = st.checkbox("Auto-assign IDs for missing Student ID cells (MCP-YY-####)")
    prefix = st.text_input("ID Prefix (for auto-assign)", value="MCP")
    year2 = st.text_input("Two-digit year (for auto-assign)", value=datetime.datetime.now().strftime("%y"))
    start_seq = st.number_input("Start sequence", min_value=1, value=1, step=1)
    logo2 = st.file_uploader("Optional logo (PNG) for batch", type=["png"], key="logo2")

    if csv_file is not None:
        # Read entire CSV
        data = csv_file.getvalue().decode("utf-8", errors="ignore")
        sio = io.StringIO(data)
        reader = csv.DictReader(sio)

        # Normalize headers -> original names
        headers_lower = {h.lower(): h for h in (reader.fieldnames or [])}
        required = ["student id", "first name", "last name"]
        if not all(h in headers_lower for h in required):
            miss = [h for h in required if h not in headers_lower]
            st.error(f"Missing required headers: {', '.join(miss)}")
        else:
            sid_h = headers_lower["student id"]
            fn_h = headers_lower["first name"]
            ln_h = headers_lower["last name"]
            gy_h = headers_lower.get("grad year")  # optional

            rows = list(reader)
            used_ids = {(r.get(sid_h) or "").strip() for r in rows if (r.get(sid_h) or "").strip()}
            gen = next_mcp_id_func(prefix, year2, start_seq, taken=used_ids)

            cards = []
            updated_rows = []
            for r in rows:
                sid = (r.get(sid_h) or "").strip()
                first = (r.get(fn_h) or "").strip()
                last = (r.get(ln_h) or "").strip()
                gy = (r.get(gy_h) or "").strip() if gy_h else ""

                if not sid and auto_assign:
                    sid = next(gen)
                    r[sid_h] = sid  # write back so it ends up in the returned CSV

                if sid and first and last:
                    cards.append({"id": sid, "first": first, "last": last, "grad_year": gy})
                updated_rows.append(r)

            missing = [r for r in rows if not ((r.get(sid_h) or "").strip() and (r.get(fn_h) or "").strip() and (r.get(ln_h) or "").strip())]
            if missing:
                st.warning(f"{len(missing)} row(s) missing id/first/last were skipped for the PDF, but kept in the updated CSV.")

            if st.button("Generate Batch PDF", type="primary"):
                pdf_bytes = make_pdf(cards, logo_file=logo2)
                st.download_button(
                    "Download Cards PDF",
                    data=pdf_bytes,
                    file_name="MCP_Cards.pdf",
                    mime="application/pdf"
                )

                # Return updated CSV (with any auto-assigned IDs)
                out_io = io.StringIO()
                writer = csv.DictWriter(out_io, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(updated_rows)
                st.download_button(
                    "Download Updated CSV (with IDs)",
                    data=out_io.getvalue().encode("utf-8"),
                    file_name="Students_With_IDs.csv",
                    mime="text/csv"
                )
