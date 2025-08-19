import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Set

SPREADSHEET_ID = st.secrets["sheets"]["spreadsheet_id"]
DEFAULT_TABS = list(st.secrets["sheets"].get("seminar_tabs", []))
STUDENT_ID_COL = st.secrets["sheets"].get("student_id_col", "B")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
gc = gspread.authorize(creds)

st.set_page_config(page_title="MCP Attendance Checker", page_icon="✅", layout="centered")
st.title("MCP Attendance Checker")

@st.cache_data(ttl=120)  # refresh every 2 minutes
def load_config_and_attendance():
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Prefer Settings tab if it exists; else use secrets
    academic_year = ""
    tabs: List[str] = DEFAULT_TABS
    try:
        ws = sh.worksheet("Settings")
        academic_year = (ws.acell("B1").value or "").strip()  # B1 next to "AcademicYear"
        # Seminar tab list in A2:A if present
        col = [v.strip() for v in ws.col_values(1)[1:] if v and v.strip()]
        if col:
            tabs = col
    except gspread.WorksheetNotFound:
        pass

    # Load each tab's StudentID column into a set
    out: dict[str, Set[str]] = {}
    col_index = ord(STUDENT_ID_COL.upper()) - ord("A") + 1
    for t in tabs:
        try:
            ws = sh.worksheet(t)
            vals = ws.col_values(col_index)
            ids = {v.strip() for v in vals if v and v.strip() and v.strip().lower() != "studentid"}
            out[t] = ids
        except gspread.WorksheetNotFound:
            out[t] = set()  # tolerate a missing tab

    return academic_year, tabs, out

year_label, seminar_tabs, attendance = load_config_and_attendance()
if year_label:
    st.caption(f"Academic year: **{year_label}**")

st.subheader("Check your attendance")
student_id = st.text_input("Enter your Student ID", placeholder="e.g., 21004335").strip()

if student_id:
    present_tabs = [t for t in seminar_tabs if student_id in attendance.get(t, set())]
    count = len(present_tabs)
    st.metric("Seminars attended", f"{count}")

    if present_tabs:
        try:
            present_tabs = sorted(present_tabs, key=lambda x: int(x))
        except:
            present_tabs.sort()
        with st.expander("Which seminars?"):
            st.write(", ".join(present_tabs))

    # Optional: full table view
    try:
        all_tabs = sorted(seminar_tabs, key=lambda x: int(x))
    except:
        all_tabs = sorted(seminar_tabs)
    st.write("Overview")
    st.table([{"Seminar": t, "Present": "✅" if student_id in attendance.get(t, set()) else "—"} for t in all_tabs])

st.caption("Counts the number of seminars you have attended throughout this year.")
