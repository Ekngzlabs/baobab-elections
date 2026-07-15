# Baobab College Elections — Streamlit version

A student election app: register with a registration number + password,
sign in, cast one ballot per position, see live results, manage
candidates from an admin page. Data lives in a local SQLite file
(`election.db`) — same idea as the CSV files in your other Streamlit
projects, just with real transactions so votes can't be double-counted.

## 1. Run it locally (Windows PowerShell)

You've done this before with `student_gpa_calculator`, so this should
look familiar:

```powershell
cd baobab-elections-streamlit
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

It'll open in your browser at `http://localhost:8501`. Try registering,
signing in, and voting. Open a second, different browser (or an
incognito window) to act as a second student and confirm they can't
see or use the first student's session.

## 2. Change the admin passcode

Open `app.py`, find this near the top:

```python
ADMIN_PASSCODE = "baobab-admin-2026"
```

Change it before you deploy.

## 3. Deploy for free — Streamlit Community Cloud

This is the easiest option since your code is already a Streamlit app.

1. Push this folder to a GitHub repo (public or private is fine).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **New app**, pick the repo/branch, and set the main file to
   `app.py`.
4. Click **Deploy**. You'll get a URL like
   `https://baobab-elections.streamlit.app` — that's what you share
   with classmates.

### A note on data persistence

`election.db` is just a file sitting next to `app.py` on whatever
server runs the app. On Streamlit Community Cloud's free tier:

- The file persists fine **while the app is actively running** — this
  is what matters during the actual voting window.
- If the app goes to sleep from inactivity and is later redeployed
  (e.g. after a code push, or a long idle period), the container can
  be recreated fresh, and `election.db` would reset with it.

For a short, real election, this is not a practical issue — students
vote, the app stays awake, you check results, done. But **do click
"Download results as CSV" on the Admin page right after voting closes**
so you have a permanent copy regardless. If you ever need it to survive
indefinitely (e.g. an election that runs for weeks with no traffic in
between), you'd want a proper hosted database instead of a local file —
happy to help set that up if it comes to that.

## 4. Managing candidates

Go to the **Admin** page, enter the passcode, and use the forms there
to add positions and candidates. Everything else (register / sign in /
vote / results) needs no login.
