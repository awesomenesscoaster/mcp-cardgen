import io, itertools, csv, streamlit as st
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from PIL import Image
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
import re, datetime

# ---------- CONFIG ----------
ORG_NAME = "Medical Certificate Program"
CARD_W, CARD_H = 3.5*inch, 2.25*inch   # standard wallet card
MARGIN_X, MARGIN_Y = 0.5*inch, 0.5*inch
COLS, ROWS = 2, 4                      # 8 per page on Letter
QR_SIZE_PX = 240
BARCODE_WIDTH_PX = 420
BARCODE_HEIGHT_PX = 120

def make_qr(data: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(str(data))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((QR_SIZE_PX, QR_SIZE_PX))

def make_code128(data: str) -> Image.Image:
    # python-barcode generates PIL via ImageWriter
    code = Code128(str(data), writer=ImageWriter())
    fp = io.BytesIO()
    code.write(fp, options={
        "module_width": 0.20,  # tune thickness
        "module_height": 16.0, # barcode height (mm-ish units)
        "font_size": 10,
        "text_distance": 1,
        "quiet_zone": 2
    })
    fp.seek(0)
    img = Image.open(fp).convert("RGB")
    return img

def draw_card(c, x, y, student_id, first, last, grad_year=None, logo_img=None):
    # Border
    c.roundRect(x, y, CARD_W, CARD_H, 10, stroke=1, fill=0)

    # QR
    qr_img = make_qr(student_id)
    qr_buf = io.BytesIO(); qr_img.save(qr_buf, format="PNG"); qr_buf.seek(0)
    c.drawImage(qr_buf, x+0.15*inch, y+0.6*inch, width=1.0*inch, height=1.0*inch, preserveAspectRatio=True, mask='auto')

    # Code128 (optional but great for 1D scanners)
    bc_img = make_code128(student_id)
    # scale barcode to fit
    bc_w_in = 1.8*inch; bc_h_in = 0.5*inch
    bc_buf = io.BytesIO(); bc_img.save(bc_buf, format="PNG"); bc_buf.seek(0)
    c.drawImage(bc_buf, x+1.35*inch, y+0.3*inch, width=bc_w_in, height=bc_h_in, preserveAspectRatio=True, mask='auto')

    # Text block
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x+1.35*inch, y+1.6*inch, f"{first} {last}".strip())
    c.setFont("Helvetica", 10)
    c.drawString(x+1.35*inch, y+1.42*inch, f"Student ID: {student_id}")
    if grad_year:
        c.drawString(x+1.35*inch, y+1.27*inch, f"Grad Year: {grad_year}")
    c.setFont("Helvetica-Oblique", 9)
    c.drawRightString(x+CARD_W-0.12*inch, y+0.15*inch, ORG_NAME)

    # Logo (optional)
    if logo_img:
        c.drawImage(logo_img, x+CARD_W-0.5*inch, y+CARD_H-0.55*inch, width=0.4*inch, height=0.4*inch, preserveAspectRatio=True, mask='auto')

def ids_in_master(existing_ids):
    # helper that returns a set for quick membership (if you want to plug your master list later)
    return set(map(str, existing_ids or []))

def next_mcp_id_func(prefix="MCP", grad_year=None, start=1, taken=None):
    # Generates IDs like MCP-26-0001; grad_year in two digits recommended
    taken = set(taken or [])
    yy = (str(grad_year)[-2:] if grad_year else datetime.datetime.now().strftime("%y"))
    base = f"{prefix}-{yy}-"
    n = start
    while True:
        candidate = f"{base}{n:04d}"
        if candidate not in taken:
            yield candidate
        n += 1

def make_pdf(cards, logo_file=None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    logo_stream = None
    if logo_file:
        logo_stream = io.BytesIO(logo_file.read()); logo_stream.seek(0)

    i = 0
    for card in cards:
        col = i % COLS
        row = (i // COLS) % ROWS
        x = MARGIN_X + col*CARD_W
        y = (letter[1] - MARGIN_Y - (row+1)*CARD_H)
        draw_card(c, x, y, card["id"], card["first"], card["last"], card.get("grad_year"), logo_stream)
        i += 1
        if i % (COLS*ROWS) == 0:
            c.showPage()
    if i % (COLS*ROWS) != 0:
        c.showPage()
    c.save()
    return buf.getvalue()

st.set_page_config(page_title="MCP Card Generator", page_icon="🪪", layout="centered")
st.title("MCP Card Generator")

tabs = st.tabs(["On-Demand", "Batch CSV"])

with tabs[0]:
    st.subheader("Generate a single card")
    first = st.text_input("First Name")
    last  = st.text_input("Last Name")
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
            pdf_bytes = make_pdf([{"id": sid, "first": first, "last": last, "grad_year": grad_year}], logo_file=logo)
            st.download_button("Download PDF", data=pdf_bytes, file_name=f"Card_{sid}.pdf", mime="application/pdf")

with tabs[1]:
    st.subheader("Batch from CSV")
    st.caption("CSV headers required: **Student ID, First Name, Last Name**. Optional: **Grad Year**.")
    csv_file = st.file_uploader("Upload CSV", type=["csv"])
    auto_assign = st.checkbox("Auto-assign IDs for missing Student ID cells (MCP-YY-####)")
    prefix = st.text_input("ID Prefix (for auto-assign)", value="MCP")
    year2 = st.text_input("Two-digit year (for auto-assign)", value=datetime.datetime.now().strftime("%y"))
    start_seq = st.number_input("Start sequence", min_value=1, value=1, step=1)
    logo2 = st.file_uploader("Optional logo (PNG) for batch", type=["png"], key="logo2")

    if csv_file is not None:
        # Read CSV once
        data = csv_file.getvalue().decode("utf-8", errors="ignore")
        sio = io.StringIO(data)
        reader = csv.DictReader(sio)

        # Normalize headers -> original names
        headers_lower = {h.lower(): h for h in reader.fieldnames or []}
        required = ["student id","first name","last name"]
        if not all(h in headers_lower for h in required):
            miss = [h for h in required if h not in headers_lower]
            st.error(f"Missing required headers: {', '.join(miss)}")
        else:
            sid_h = headers_lower["student id"]
            fn_h  = headers_lower["first name"]
            ln_h  = headers_lower["last name"]
            gy_h  = headers_lower.get("grad year")  # optional

            rows = list(reader)
            used_ids = { (r.get(sid_h) or "").strip() for r in rows if (r.get(sid_h) or "").strip() }
            gen = next_mcp_id_func(prefix, year2, start_seq, taken=used_ids)

            cards = []
            updated_rows = []
            for r in rows:
                sid = (r.get(sid_h) or "").strip()
                first = (r.get(fn_h) or "").strip()
                last  = (r.get(ln_h) or "").strip()
                grad_year = (r.get(gy_h) or "").strip() if gy_h else ""

                if not sid and auto_assign:
                    sid = next(gen)
                    r[sid_h] = sid  # write back so it ends up in the returned CSV

                # collect valid cards
                if sid and first and last:
                    cards.append({"id": sid, "first": first, "last": last, "grad_year": grad_year})
                updated_rows.append(r)

            missing = [r for r in rows if not ((r.get(sid_h) or "").strip() and (r.get(fn_h) or "").strip() and (r.get(ln_h) or "").strip())]
            if missing:
                st.warning(f"{len(missing)} row(s) missing id/first/last were skipped for the PDF, but kept in the updated CSV.")

            if st.button("Generate Batch PDF", type="primary"):
                pdf_bytes = make_pdf(cards, logo_file=logo2)
                st.download_button("Download Cards PDF", data=pdf_bytes, file_name="MCP_Cards.pdf", mime="application/pdf")

                # Return updated CSV (with any auto-assigned IDs)
                out_io = io.StringIO()
                writer = csv.DictWriter(out_io, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(updated_rows)
                st.download_button("Download Updated CSV (with IDs)", data=out_io.getvalue().encode("utf-8"),
                                   file_name="Students_With_IDs.csv", mime="text/csv")