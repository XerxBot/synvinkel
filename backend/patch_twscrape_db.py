"""Patch twscrape accounts.db with cookie-based auth from environment."""
import json
import os
import sqlite3
from urllib.parse import unquote

from app.config import settings

cookie_str = settings.TWITTER_COOKIES
username = settings.TWITTER_USERNAME or "xeon64"
password = settings.TWITTER_PASSWORD or ""

if not cookie_str:
    print("ERROR: TWITTER_COOKIES is empty in settings")
    exit(1)

# Parse cookie string → dict
cookies: dict[str, str] = {}
for part in cookie_str.split("; "):
    if "=" in part:
        k, v = part.split("=", 1)
        cookies[k.strip()] = unquote(v.strip())

print(f"Parsed {len(cookies)} cookies: {list(cookies.keys())}")
print(f"auth_token present: {'auth_token' in cookies}")
print(f"ct0 present: {'ct0' in cookies}")
print(f"twid: {cookies.get('twid', 'MISSING')}")

ct0 = cookies.get("ct0", "")
bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I7BeIqxRo8H%3DUQ2DDjlGsQ3gDR0"
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
headers = {
    "x-csrf-token": ct0,
    "authorization": f"Bearer {bearer}",
}

db_path = os.environ.get("TWSCRAPE_DB", "accounts.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("DELETE FROM accounts WHERE username=?", (username,))
cur.execute(
    """INSERT INTO accounts
       (username, password, email, email_password, user_agent, active, locks, headers, cookies, stats)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        username, password, username, password,
        ua, True, "{}", json.dumps(headers), json.dumps(cookies), "{}",
    ),
)
conn.commit()
cur.execute("SELECT username, active, length(cookies) FROM accounts")
rows = cur.fetchall()
conn.close()

print(f"DB patched — accounts: {rows}")
print("Done. Run collect_statements --source twitter to test.")
