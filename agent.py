"""
Barca Match Agent
------------------
Checks FC Barcelona's upcoming matches via football-data.org and:
  1. Sends an EMAIL ~24h before kickoff, naming the opponent.
  2. Sends a TELEGRAM message right after kickoff.

Meant to run on a schedule (every 15 min) via GitHub Actions.
State (which matches we've already notified about) lives in state.json
so we never send the same notification twice between runs.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
import requests

BARCELONA_TEAM_ID = 81  # FC Barcelona's id on football-data.org
STATE_FILE = "state.json"

FOOTBALL_API_TOKEN = os.environ["FOOTBALL_API_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
EMAIL_TO = os.environ["EMAIL_TO"]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"reminded": [], "started": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_upcoming_matches():
    """Fetch Barcelona's scheduled matches for the next 2 days (all competitions)."""
    today = datetime.now(timezone.utc).date()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=2)).isoformat()

    url = f"https://api.football-data.org/v4/teams/{BARCELONA_TEAM_ID}/matches"
    params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}
    headers = {"X-Auth-Token": FOOTBALL_API_TOKEN}

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("matches", [])


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = EMAIL_TO

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)


def opponent_name(match):
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]
    return away if home == "FC Barcelona" else home


def main():
    state = load_state()
    matches = get_upcoming_matches()
    now = datetime.now(timezone.utc)
    changed = False

    for match in matches:
        match_id = str(match["id"])
        kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        hours_until = (kickoff - now).total_seconds() / 3600
        minutes_since = (now - kickoff).total_seconds() / 60
        opponent = opponent_name(match)
        competition = match["competition"]["name"]

        # 24h-before reminder — fires once, in the 23-25h window before kickoff
        if 23 <= hours_until <= 25 and match_id not in state["reminded"]:
            kickoff_local = kickoff.strftime("%d.%m.%Y u %H:%M UTC")
            send_email(
                subject=f"Barca sutra igra protiv {opponent}!",
                body=(
                    f"FC Barcelona igra protiv {opponent} ({competition}) "
                    f"za otprilike 24 sata.\n\nPocetak: {kickoff_local}"
                ),
            )
            state["reminded"].append(match_id)
            changed = True

        # Kickoff notification — fires once, within 20 min after kickoff
        if 0 <= minutes_since <= 20 and match_id not in state["started"]:
            send_telegram(f"Utakmica je pocela! Barcelona vs {opponent} ({competition})")
            state["started"].append(match_id)
            changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
