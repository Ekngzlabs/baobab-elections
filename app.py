"""
Baobab College Elections — Streamlit + SQLite

A student election app:
- Students register once with a registration number + password.
- They sign in and cast one ballot (one candidate per position).
- SQLite's PRIMARY KEY and a guarded transaction make sure a
  registration number can never register twice or vote twice,
  even if two people submit at the exact same moment.
- Results are visible live; admins can manage candidates.

Run locally:      streamlit run app.py
Deploy for free:  Streamlit Community Cloud (see README.md)
"""

import sqlite3
import hashlib
import io
from contextlib import closing

import pandas as pd
import streamlit as st

DB_PATH = "election.db"
ADMIN_PASSCODE = "BIT 15"  # change this before you deploy!

DEFAULT_POSITIONS = {
    "President": [
        ("Raphael Mugama", "CMT"),
        ("David Magor", " SAT"),
        ("Jimila Miraj","PST")
    ],
    "Vice President": [
        ("Angel Mwabulambo", " PST"),
        ("Enock Rwekaza", " SAT"),
        ("Miraj Makanza","SAT" )
    ],
    "Genaral Secretary": [
        ("Fatuma", "CMT"),
        ("Jafari Cletus", "SAT"),
    ],
}


# ----------------------------- Database setup -----------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS students (
                reg_no TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                has_voted INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position TEXT NOT NULL,
                name TEXT NOT NULL,
                note TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            )"""
        )
        # Seed default candidates only the very first time the app runs
        count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        if count == 0:
            for position, cands in DEFAULT_POSITIONS.items():
                for name, note in cands:
                    conn.execute(
                        "INSERT INTO candidates (position, name, note) VALUES (?, ?, ?)",
                        (position, name, note),
                    )


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_reg(reg: str) -> str:
    return reg.strip().upper().replace(" ", "")


# ----------------------------- Data access -----------------------------

def get_student(reg_no):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT reg_no, password_hash, has_voted FROM students WHERE reg_no = ?",
            (reg_no,),
        ).fetchone()
        return row


def register_student(reg_no, password) -> tuple[bool, str]:
    try:
        with closing(get_conn()) as conn, conn:
            conn.execute(
                "INSERT INTO students (reg_no, password_hash, has_voted) VALUES (?, ?, 0)",
                (reg_no, hash_password(password)),
            )
        return True, f"Registered {reg_no}. You can sign in now."
    except sqlite3.IntegrityError:
        return False, f"{reg_no} is already registered. Sign in instead."


def get_positions():
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT id, position, name, note FROM candidates ORDER BY position, id"
        ).fetchall()
    positions = {}
    for cid, position, name, note in rows:
        positions.setdefault(position, []).append({"id": cid, "name": name, "note": note})
    return positions


def cast_vote(reg_no, candidate_ids: list[int]) -> tuple[bool, str]:
    """Atomically: confirm the student hasn't voted, record the ballot,
    and flip has_voted — all inside one transaction so a double-submit
    or two simultaneous voters can never be counted twice."""
    with closing(get_conn()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE students SET has_voted = 1 WHERE reg_no = ? AND has_voted = 0",
                (reg_no,),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                return False, "This registration number has already voted."
            for cid in candidate_ids:
                conn.execute("INSERT INTO votes (candidate_id) VALUES (?)", (cid,))
            conn.execute("COMMIT")
            return True, "Ballot cast. Your vote has been recorded."
        except Exception as e:
            conn.execute("ROLLBACK")
            return False, f"Could not cast your ballot: {e}"


def get_tally():
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """SELECT c.position, c.name, COUNT(v.id) as votes
               FROM candidates c
               LEFT JOIN votes v ON v.candidate_id = c.id
               GROUP BY c.id
               ORDER BY c.position, c.id"""
        ).fetchall()
    return pd.DataFrame(rows, columns=["Position", "Candidate", "Votes"])


def add_candidate(position, name, note):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO candidates (position, name, note) VALUES (?, ?, ?)",
            (position.strip(), name.strip(), note.strip()),
        )


def add_position(position):
    # Positions only really exist once they have a candidate, but we let
    # the admin "create" an empty one by inserting a placeholder-free
    # marker row that's filtered out of voting/results if it has no name.
    with closing(get_conn()) as conn, conn:
        exists = conn.execute(
            "SELECT 1 FROM candidates WHERE position = ? LIMIT 1", (position.strip(),)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO candidates (position, name, note) VALUES (?, '(no candidates yet)', '')",
                (position.strip(),),
            )


# ----------------------------- Streamlit UI -----------------------------

st.set_page_config(page_title="Baobab College Elections", page_icon="🗳️", layout="centered")
init_db()

if "reg_no" not in st.session_state:
    st.session_state.reg_no = None
if "has_voted" not in st.session_state:
    st.session_state.has_voted = False
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}
h1, h2, h3 {
    font-family: 'Fraunces', serif !important;
    color: #1B2A2A;
}
[data-testid="stSidebar"] {
    background-color: #EFE7D2;
    border-right: 1px solid rgba(27,42,42,0.12);
}
.stButton > button {
    border-radius: 4px;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.baobab-header { display: flex; align-items: center; gap: 14px; padding: 6px 0 2px; }
.baobab-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12.5px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #6E6657;
    margin-top: -6px;
}
</style>
<div class="baobab-header">
  <svg width="46" height="46" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="32" cy="18" rx="20" ry="14" fill="#1F6F4B"/>
    <ellipse cx="18" cy="14" rx="10" ry="8" fill="#2f8a60"/>
    <ellipse cx="46" cy="14" rx="10" ry="8" fill="#2f8a60"/>
    <rect x="27" y="28" width="10" height="24" rx="3" fill="#8a5a2e"/>
    <ellipse cx="32" cy="54" rx="16" ry="4" fill="#C99A2E" opacity="0.5"/>
  </svg>
  <div>
    <h1 style="margin-bottom:0;">Baobab College Elections</h1>
    <div class="baobab-subtitle">2026 Student Union &middot; one vote per registration number</div>
  </div>
</div>
""", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigate",
    ["Register", "Sign in", "Cast ballot", "Results", "Admin"],
    index=0,
)

if st.session_state.reg_no:
    st.sidebar.markdown("---")
    st.sidebar.write(f"Signed in: **{st.session_state.reg_no}**")
    st.sidebar.write("Ballot status: " + ("✅ sealed" if st.session_state.has_voted else "🕓 not yet cast"))
    if st.sidebar.button("Sign out"):
        st.session_state.reg_no = None
        st.session_state.has_voted = False
        st.rerun()

# ---------- Register ----------
if page == "Register":
    st.subheader("Register to vote")
    st.write(
        "Enter your registration number once and create a password. "
        "Each registration number can register only once and vote only once."
    )
    with st.form("register_form"):
        reg = st.text_input("Registration number", placeholder="e.g. BIT/AIML/2026/014")
        pw = st.text_input("Create password (min. 6 characters)", type="password")
        pw2 = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Register")

    if submitted:
        reg_norm = normalize_reg(reg)
        if not reg_norm:
            st.error("Enter your registration number.")
        elif len(pw) < 6:
            st.error("Password needs at least 6 characters.")
        elif pw != pw2:
            st.error("Passwords do not match.")
        else:
            ok, msg = register_student(reg_norm, pw)
            (st.success if ok else st.error)(msg)

    st.caption(
        "Passwords are hashed (SHA-256) before they're stored — the plain "
        "password is never saved."
    )

# ---------- Sign in ----------
elif page == "Sign in":
    st.subheader("Sign in")
    with st.form("login_form"):
        reg = st.text_input("Registration number")
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        reg_norm = normalize_reg(reg)
        student = get_student(reg_norm)
        if not student:
            st.error("No record for that registration number. Register first.")
        elif student[1] != hash_password(pw):
            st.error("Incorrect password.")
        else:
            st.session_state.reg_no = reg_norm
            st.session_state.has_voted = bool(student[2])
            st.success(f"Signed in as {reg_norm}.")
            st.rerun()

# ---------- Cast ballot ----------
elif page == "Cast ballot":
    st.subheader("Cast your ballot")
    if not st.session_state.reg_no:
        st.info("Sign in first to vote.")
    elif st.session_state.has_voted:
        st.success("You've already cast a ballot for this election. Check the Results page.")
    else:
        positions = get_positions()
        st.write("Choose one candidate per position, then cast your ballot.")
        selections = {}
        for position, cands in positions.items():
            real_cands = [c for c in cands if c["name"] != "(no candidates yet)"]
            if not real_cands:
                continue
            st.markdown(f"**{position}**")
            options = {f'{c["name"]} — {c["note"]}': c["id"] for c in real_cands}
            choice = st.radio(position, list(options.keys()), key=f"pos_{position}", label_visibility="collapsed")
            selections[position] = options[choice]
            st.markdown("---")

        if st.button("Cast ballot", type="primary"):
            if len(selections) < len([p for p, c in positions.items() if any(x["name"] != "(no candidates yet)" for x in c)]):
                st.error("Please choose a candidate for every position.")
            else:
                ok, msg = cast_vote(st.session_state.reg_no, list(selections.values()))
                if ok:
                    st.session_state.has_voted = True
                    st.success(msg)
                    st.balloons()
                else:
                    st.error(msg)
                    if "already voted" in msg:
                        st.session_state.has_voted = True

# ---------- Results ----------
elif page == "Results":
    st.subheader("Live results")
    df = get_tally()
    df = df[df["Candidate"] != "(no candidates yet)"]
    if df.empty:
        st.info("No candidates set up yet.")
    else:
        total_ballots = df.groupby("Position")["Votes"].sum().max() if not df.empty else 0
        for position in df["Position"].unique():
            st.markdown(f"### {position}")
            sub = df[df["Position"] == position].set_index("Candidate")
            st.bar_chart(sub["Votes"])
            total = sub["Votes"].sum()
            for name, votes in sub["Votes"].items():
                pct = round(votes / total * 100) if total else 0
                st.write(f"- **{name}**: {votes} vote(s) ({pct}%)")

# ---------- Admin ----------
elif page == "Admin":
    st.subheader("Admin")
    if not st.session_state.admin_unlocked:
        passcode = st.text_input("Admin passcode", type="password")
        if st.button("Unlock"):
            if passcode == ADMIN_PASSCODE:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Wrong passcode.")
        st.caption(
            "This passcode only keeps casual visitors out — it lives in the "
            "app's source code, so change it, and don't rely on it alone."
        )
    else:
        st.markdown("#### Add a candidate")
        positions = get_positions()
        position_names = list(positions.keys()) or ["Student Union President"]
        with st.form("add_candidate_form"):
            position = st.selectbox("Position", position_names)
            name = st.text_input("Candidate name")
            note = st.text_input("Note (year / programme)")
            if st.form_submit_button("Add candidate"):
                if name.strip():
                    add_candidate(position, name, note)
                    st.success("Candidate added.")
                    st.rerun()
                else:
                    st.error("Enter a candidate name.")

        st.markdown("#### Add a position")
        with st.form("add_position_form"):
            new_pos = st.text_input("Position title")
            if st.form_submit_button("Add position"):
                if new_pos.strip():
                    add_position(new_pos)
                    st.success("Position added.")
                    st.rerun()
                else:
                    st.error("Enter a position title.")

        st.markdown("#### Backup results")
        df = get_tally()
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button(
            "Download results as CSV",
            csv_buf.getvalue(),
            file_name="baobab_election_results.csv",
            mime="text/csv",
        )
        st.caption(
            "Download a backup after voting closes — SQLite storage on some "
            "free hosts is not guaranteed to be permanent long-term."
        )
