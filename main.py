import os
import re
import json
import hashlib
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

DISCOVERY_THRESHOLD = int(os.getenv("DISCOVERY_SCORE", "50"))
ALERT_THRESHOLD = int(os.getenv("MIN_SCORE", "70"))

MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "14"))

SEEN_FILE = "seen.json"


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCHES = [
    '"prop firm" giveaway',
    '"prop firm" giveaway 2026',
    '"prop firm" contest',
    '"prop firm" competition',
    '"prop trading" giveaway',
    '"prop trading" contest',
    '"funded account" giveaway',
    '"funded account" contest',
    '"funded trader" giveaway',
    '"funded trader" contest',
    '"free prop firm" challenge',
    '"free funded account" challenge',
    '"trading challenge" giveaway',
    '"prop firm" sweepstakes',
    '"trading account" giveaway',
    '"funded account" free',
    '"free trading challenge" prop firm',
]


# ============================================================
# KNOWN PROP FIRMS
# ============================================================

PROP_FIRMS = [
    "FTMO",
    "FundedNext",
    "The5ers",
    "FundingPips",
    "E8 Markets",
    "E8",
    "Funded Trading Plus",
    "Funded Trader Markets",
    "FundedFirm",
    "Hola Prime",
    "Tradeify",
    "MyFundedFX",
    "Topstep",
    "Apex Trader Funding",
    "Apex",
    "Take Profit Trader",
    "MFF",
    "MFFX",
    "Futures Elite",
    "FXIFY",
    "Blue Guardian",
    "Goat Funded Trader",
    "Instant Funding",
    "Funded Trading Plus",
    "Lux Trading Firm",
    "Alpha Capital Group",
    "The Funded Trader",
    "Funding Traders",
    "Finotive Funding",
    "Ment Funding",
    "DNA Funded",
    "FundedNext",
    "OneUp Trader",
    "Bulenox",
]


# ============================================================
# GIVEAWAY / ENTRY WORDS
# ============================================================

GIVEAWAY_WORDS = [
    "giveaway",
    "give away",
    "sweepstakes",
    "win",
    "winner",
    "prize",
    "prizes",
    "free account",
    "free funded account",
    "free challenge",
    "free prop firm challenge",
    "free trading account",
]


ENTRY_WORDS = [
    "enter",
    "entry",
    "join",
    "register",
    "participate",
    "sign up",
    "signup",
    "retweet",
    "repost",
    "follow",
    "like",
    "comment",
    "share",
    "tag",
    "competition",
    "contest",
]


ACTIVE_WORDS = [
    "open now",
    "open",
    "ongoing",
    "active",
    "currently",
    "enter now",
    "entries open",
    "registration open",
    "register now",
    "join now",
    "ends",
    "deadline",
    "until",
    "closes",
    "closing",
    "last chance",
    "still available",
]


EXCLUDE_WORDS = [
    "ended",
    "ends 2024",
    "ended 2024",
    "ends 2025",
    "ended 2025",
    "2024 giveaway",
    "2025 giveaway",
    "historical",
    "old giveaway",
    "past giveaway",
    "crypto airdrop",
    "token giveaway",
    "nft giveaway",
    "casino",
    "sports betting",
]


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing")

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")

    return True


# ============================================================
# TELEGRAM CONNECTION TEST
# ============================================================

def telegram_test():
    message = (
        "✅ Prop-Firm Giveaway Hunter\n\n"
        "Telegram connection test successful.\n"
        f"Discovery threshold: {DISCOVERY_THRESHOLD}/100\n"
        f"Alert threshold: {ALERT_THRESHOLD}/100"
    )

    send_telegram(message)


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news(query):
    try:
        encoded = quote_plus(query)

        url = (
            "https://news.google.com/rss/search?"
            f"q={encoded}&hl=en-US&gl=US&ceid=US:en"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

        return feedparser.parse(response.content)

    except Exception as e:
        print("Feed error:", e)
        return None


# ============================================================
# CLEAN TEXT
# ============================================================

def clean(text):
    if not text:
        return ""

    text = html.unescape(text)

    soup = BeautifulSoup(
        text,
        "html.parser"
    )

    return soup.get_text(" ", strip=True)


# ============================================================
# RECENCY
# ============================================================

def recent_entry(entry):

    try:

        if hasattr(entry, "published_parsed"):

            published = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

            age = datetime.now(timezone.utc) - published

            return age <= timedelta(days=MAX_AGE_DAYS)

    except Exception:
        pass

    # If date cannot be read, keep it.
    return True


# ============================================================
# IDENTIFY FIRM
# ============================================================

def identify_firm(text):

    text_lower = text.lower()

    # First check known firms.
    for firm in PROP_FIRMS:

        if firm.lower() in text_lower:
            return firm

    # Try common generic firm names.
    patterns = [
        r"\b([A-Z][A-Za-z0-9&.-]{2,30}\s+(?:Markets|Funding|Capital|Trading|Trader|Firm))\b",
        r"\b([A-Z][A-Za-z0-9&.-]{2,30}\s+Prop)\b",
    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:
            return match.group(1).strip()

    return "Unknown Prop Firm"


# ============================================================
# DEADLINE EXTRACTION
# ============================================================

def extract_deadline(text):

    patterns = [

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|:|-)?\s*"
        r"([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)",

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|:|-)?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|:|-)?\s*"
        r"(\d{4}-\d{2}-\d{2})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# SCORE
# ============================================================

def score_item(title, summary):

    text = f"{title} {summary}".lower()

    giveaway_hits = sum(
        1
        for word in GIVEAWAY_WORDS
        if word in text
    )

    entry_hits = sum(
        1
        for word in ENTRY_WORDS
        if word in text
    )

    active_hits = sum(
        1
        for word in ACTIVE_WORDS
        if word in text
    )

    prop_hits = sum(
        1
        for firm in PROP_FIRMS
        if firm.lower() in text
    )

    score = 0

    # Giveaway evidence
    score += min(giveaway_hits * 15, 30)

    # Entry/action evidence
    score += min(entry_hits * 8, 20)

    # Active evidence
    score += min(active_hits * 10, 20)

    # Prop-firm evidence
    score += min(prop_hits * 15, 30)

    # Money/prize evidence
    if "$" in text:
        score += 5

    if "funded" in text:
        score += 5

    if "account" in text:
        score += 5

    # Strong penalty for obvious old material.
    for word in EXCLUDE_WORDS:

        if word in text:
            score -= 40

    score = max(0, min(score, 100))

    return score


# ============================================================
# VALIDATE GIVEAWAY
# ============================================================

def analyse_entry(entry):

    title = clean(entry.get("title", ""))
    summary = clean(entry.get("summary", ""))
    link = entry.get("link", "").strip()

    if not title:
        return None

    if not recent_entry(entry):
        return None

    text = f"{title} {summary}"

    text_lower = text.lower()

    # Must contain giveaway evidence.
    giveaway_hits = sum(
        1
        for word in GIVEAWAY_WORDS
        if word in text_lower
    )

    if giveaway_hits == 0:
        return None

    # Must contain some prop-firm/trading evidence.
    prop_context = (
        "prop firm" in text_lower
        or "prop trading" in text_lower
        or "funded account" in text_lower
        or "funded trader" in text_lower
        or "trading challenge" in text_lower
        or "propfirm" in text_lower
        or any(
            firm.lower() in text_lower
            for firm in PROP_FIRMS
        )
    )

    if not prop_context:
        return None

    # Reject obvious non-prop giveaways.
    for word in EXCLUDE_WORDS:

        if word in text_lower:
            return None

    score = score_item(title, summary)

    if score < DISCOVERY_THRESHOLD:
        return None

    firm = identify_firm(text)

    deadline = extract_deadline(text)

    return {
        "firm": firm,
        "title": title,
        "summary": summary[:1200],
        "link": link,
        "score": score,
        "deadline": deadline,
    }


# ============================================================
# ID
# ============================================================

def make_id(title, link):

    raw = f"{title}|{link}".encode()

    return hashlib.sha256(raw).hexdigest()


# ============================================================
# SEEN DATABASE
# ============================================================

def load_seen():

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(json.load(f))

    except Exception:

        return set()


def save_seen(seen):

    # Keep the file manageable.
    recent = list(seen)[-5000:]

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            recent,
            f,
            indent=2
        )


# ============================================================
# FORMAT ALERT
# ============================================================

def format_alert(item):

    deadline = (
        item["deadline"]
        if item["deadline"]
        else "Not detected"
    )

    return (
        "🚨 ACTIVE PROP-FIRM GIVEAWAY\n\n"

        f"🏢 Firm: {item['firm']}\n\n"

        f"🎁 {item['title']}\n\n"

        f"⭐ Confidence: {item['score']}/100\n\n"

        f"📅 Deadline: {deadline}\n\n"

        f"📝 {item['summary']}\n\n"

        f"🔗 ENTER / SOURCE:\n{item['link']}"
    )


# ============================================================
# SCANNER
# ============================================================

def scan():

    seen = load_seen()

    candidates = {}

    total_results = 0

    print("=" * 60)
    print("PROP-FIRM GIVEAWAY HUNTER")
    print("=" * 60)

    for query in SEARCHES:

        print(f'Searching: "{query}"')

        feed = google_news(query)

        if not feed:
            continue

        for entry in feed.entries:

            total_results += 1

            item = analyse_entry(entry)

            if not item:
                continue

            uid = make_id(
                item["title"],
                item["link"]
            )

            # Avoid duplicate articles from multiple searches.
            candidates[uid] = item

    print()
    print(f"RAW RESULTS: {total_results}")
    print(f"DISCOVERED CANDIDATES: {len(candidates)}")

    # --------------------------------------------------------
    # Alert qualifying items
    # --------------------------------------------------------

    alerts = []

    for uid, item in candidates.items():

        if item["score"] < ALERT_THRESHOLD:
            continue

        if uid in seen:
            continue

        alerts.append(
            (uid, item)
        )

    print(
        f"QUALIFYING ALERTS: {len(alerts)}"
    )

    # --------------------------------------------------------
    # Send alerts
    # --------------------------------------------------------

    for uid, item in alerts:

        try:

            message = format_alert(item)

            send_telegram(message)

            print(
                f"TELEGRAM SENT | "
                f"{item['firm']} | "
                f"{item['score']}/100"
            )

            seen.add(uid)

        except Exception as e:

            print(
                "TELEGRAM ERROR:",
                e
            )

    save_seen(seen)

    # --------------------------------------------------------
    # Scan summary
    # --------------------------------------------------------

    if alerts:

        summary = (
            "🔎 Prop-Firm Giveaway Hunter\n\n"
            f"Scan completed successfully.\n\n"
            f"🚨 New qualifying giveaways: "
            f"{len(alerts)}\n\n"
            f"🔎 Discovery threshold: "
            f"{DISCOVERY_THRESHOLD}/100\n"
            f"🚨 Alert threshold: "
            f"{ALERT_THRESHOLD}/100"
        )

    else:

        summary = (
            "🔎 Prop-Firm Giveaway Hunter\n\n"
            "Scan completed successfully.\n\n"
            "No new qualifying active "
            "prop-firm giveaways found.\n\n"
            f"🔎 Discovery threshold: "
            f"{DISCOVERY_THRESHOLD}/100\n"
            f"🚨 Alert threshold: "
            f"{ALERT_THRESHOLD}/100\n\n"
            f"📰 Results scanned: "
            f"{total_results}\n"
            f"🎯 Candidates discovered: "
            f"{len(candidates)}"
        )

    try:

        send_telegram(summary)

    except Exception as e:

        print(
            "SUMMARY TELEGRAM ERROR:",
            e
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        scan()

    except Exception as e:

        print(
            "FATAL SCANNER ERROR:",
            repr(e)
        )

        # Try to notify Telegram.
        try:

            send_telegram(
                "❌ Prop-Firm Giveaway Hunter ERROR\n\n"
                f"{e}"
            )

        except Exception:
            pass

        raise
