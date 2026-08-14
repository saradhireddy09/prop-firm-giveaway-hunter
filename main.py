import os
import re
import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"

DISCOVERY_THRESHOLD = 50
ALERT_THRESHOLD = 70

MAX_AGE_DAYS = 30
MAX_RESULTS_PER_QUERY = 50
MAX_DISCOVERY_REPORT = 20

REQUEST_TIMEOUT = 20

# ------------------------------------------------------------
# Search queries
# ------------------------------------------------------------

SEARCHES = [
    '"prop firm" giveaway',
    '"prop trading" giveaway',
    '"funded account" giveaway',
    '"funded trader" giveaway',
    '"free prop firm" challenge',
    '"prop firm" sweepstakes',
    '"trading challenge" giveaway',
    '"funded account" contest',
    '"funded trader" contest',
    '"prop firm" free challenge',
    '"free funded account"',
    '"free trading account" prop firm',
    '"prop firm" "$" giveaway',
    '"prop firm" prize',
    '"funded account" prize',
    '"prop firm" competition',
    '"trading competition" funded account',
    '"prop firm" promotion',
    '"prop firm" anniversary giveaway',
    '"prop firm" birthday giveaway',
    '"prop firm" anniversary contest',
]


# ============================================================
# KNOWN PROP FIRMS
# ============================================================

PROP_FIRMS = [
    "FTMO",
    "FundedNext",
    "FundingPips",
    "The5ers",
    "E8 Markets",
    "E8 Funding",
    "Funded Trading Plus",
    "Funded Trader Markets",
    "FundedFirm",
    "FundedFirmX",
    "Hola Prime",
    "Tradeify",
    "Topstep",
    "Apex Trader Funding",
    "MyFundedFX",
    "FXIFY",
    "Funding Traders",
    "Alpha Capital Group",
    "Blueberry Funded",
    "FunderPro",
    "Lux Trading Firm",
    "Fidelcrest",
    "Goat Funded Trader",
    "The Funded Trader",
    "True Forex Funds",
    "City Traders Imperium",
    "Instant Funding",
    "Funded Trading",
    "FundedNext Futures",
    "BrightFunded",
    "Ment Funding",
    "Finotive Funding",
    "Audacity Capital",
    "Maven Trading",
    "Funded Peaks",
    "Trade The Pool",
    "OneUp Trader",
    "Take Profit Trader",
    "Earn2Trade",
    "TickTickTrader",
    "Bulenox",
    "TradeDay",
]


# ============================================================
# KEYWORDS
# ============================================================

GIVEAWAY_WORDS = [
    "giveaway",
    "giveaways",
    "sweepstakes",
    "contest",
    "competition",
    "prize",
    "prizes",
    "win",
    "winning",
    "winner",
    "free account",
    "free challenge",
    "free funded account",
    "free prop firm",
    "free trading account",
]

ENTRY_WORDS = [
    "enter",
    "entry",
    "entries",
    "join",
    "register",
    "registration",
    "sign up",
    "signup",
    "participate",
    "follow",
    "like",
    "comment",
    "share",
    "referral",
    "code",
    "coupon",
]

ACTIVE_WORDS = [
    "now",
    "open",
    "ongoing",
    "active",
    "live",
    "enter now",
    "join now",
    "register now",
    "ends",
    "ending",
    "deadline",
    "until",
    "expires",
    "available",
    "currently",
]

EXPIRED_WORDS = [
    "ended",
    "winner announced",
    "winners announced",
    "closed",
    "expired",
    "past giveaway",
    "last year",
    "2023",
    "2024",
    "2025",
]

PROP_CONTEXT_WORDS = [
    "prop firm",
    "prop trading",
    "funded trader",
    "funded account",
    "funded challenge",
    "trading challenge",
    "proprietary trading",
    "trading firm",
]


# ============================================================
# CONFIG LOADER
# ============================================================

def load_config():
    """
    Expected config.json:

    {
        "telegram_bot_token": "YOUR_BOT_TOKEN",
        "telegram_chat_id": "YOUR_CHAT_ID"
    }
    """

    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            "config.json not found. Create it with telegram_bot_token "
            "and telegram_chat_id."
        )

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")

    if not token or not chat_id:
        raise ValueError(
            "config.json must contain telegram_bot_token and telegram_chat_id."
        )

    return config


# ============================================================
# SEEN DATABASE
# ============================================================

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return set(data)

    except Exception:
        pass

    return set()


def save_seen(seen):
    try:
        # Keep the database from becoming enormous.
        values = list(seen)[-5000:]

        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2)

    except Exception as e:
        print("Seen save error:", e)


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    config = load_config()

    token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

    return True


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news(query):
    """
    Search Google News through RSS.
    """

    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                )
            },
        )

        response.raise_for_status()

        return feedparser.parse(response.content)

    except Exception as e:
        print("Feed error:", e)
        return None


# ============================================================
# TEXT CLEANING
# ============================================================

def clean(text):
    if not text:
        return ""

    try:
        return BeautifulSoup(
            str(text),
            "html.parser"
        ).get_text(" ", strip=True)

    except Exception:
        return str(text)


# ============================================================
# ID
# ============================================================

def make_id(title, link):
    raw = f"{title}|{link}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# FIRM IDENTIFICATION
# ============================================================

def identify_firm(text):
    text_lower = text.lower()

    for firm in PROP_FIRMS:
        if firm.lower() in text_lower:
            return firm

    return "Unknown"


# ============================================================
# RECENT ENTRY
# ============================================================

def recent_entry(entry):
    """
    Reject clearly old articles when a date is available.
    """

    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc,
            )

            age = datetime.now(timezone.utc) - published

            return age <= timedelta(days=MAX_AGE_DAYS)

    except Exception:
        pass

    # If Google does not provide a usable date,
    # don't automatically reject the result.
    return True


# ============================================================
# DEADLINE DETECTION
# ============================================================

def detect_deadline(text):
    """
    Try to find common giveaway deadline language.
    """

    patterns = [
        r"(?:ends?|ending|deadline|expires?|until)\s+"
        r"([A-Za-z0-9 ,./-]{3,40})",

        r"(?:ends?|ending)\s+(?:on\s+)?"
        r"([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?)",

        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"([A-Za-z]+\s+\d{1,2},\s*\d{4})",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            value = match.group(1).strip()

            if len(value) > 60:
                continue

            return value

    return None


# ============================================================
# ACTIVE CHECK
# ============================================================

def is_expired(text):
    lower = text.lower()

    for word in EXPIRED_WORDS:
        if word in lower:
            return True

    return False


def active_signal(text):
    lower = text.lower()

    return sum(
        1
        for word in ACTIVE_WORDS
        if word in lower
    )


# ============================================================
# ANALYSIS / SCORING
# ============================================================

def analyse_entry(title, summary, link):
    """
    IMPORTANT:

    This function deliberately DOES NOT reject candidates
    just because their score is below 50.

    Discovery and alerting are separate.
    """

    text = f"{title} {summary} {link}"
    lower = text.lower()

    firm = identify_firm(text)

    giveaway_hits = sum(
        1
        for word in GIVEAWAY_WORDS
        if word in lower
    )

    entry_hits = sum(
        1
        for word in ENTRY_WORDS
        if word in lower
    )

    active_hits = sum(
        1
        for word in ACTIVE_WORDS
        if word in lower
    )

    prop_context_hits = sum(
        1
        for word in PROP_CONTEXT_WORDS
        if word in lower
    )

    # --------------------------------------------------------
    # Basic candidate detection
    # --------------------------------------------------------

    if giveaway_hits == 0 and firm == "Unknown":
        return None

    if prop_context_hits == 0 and firm == "Unknown":
        return None

    # Clearly expired content is not an active giveaway.
    if is_expired(text):
        return None

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    score = 0

    # Giveaway evidence
    score += min(giveaway_hits * 15, 35)

    # Entry/action evidence
    score += min(entry_hits * 8, 24)

    # Active evidence
    score += min(active_hits * 10, 30)

    # Prop firm identification
    if firm != "Unknown":
        score += 20

    # Strong prop context
    score += min(prop_context_hits * 5, 15)

    # Money/prize
    if "$" in text:
        score += 5

    if "£" in text or "€" in text:
        score += 5

    # Free account/challenge
    if "free funded account" in lower:
        score += 15

    if "free challenge" in lower:
        score += 10

    if "free account" in lower:
        score += 8

    # Direct entry language
    if "enter now" in lower:
        score += 10

    if "join now" in lower:
        score += 8

    if "register now" in lower:
        score += 8

    # Prize language
    if "cash prize" in lower:
        score += 8

    if "funded account" in lower and "prize" in lower:
        score += 10

    # --------------------------------------------------------
    # Cap score
    # --------------------------------------------------------

    score = min(score, 100)

    deadline = detect_deadline(text)

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if score >= ALERT_THRESHOLD:
        status = "ALERT"

    elif score >= DISCOVERY_THRESHOLD:
        status = "DISCOVERY"

    else:
        status = "LOW"

    return {
        "firm": firm,
        "title": title,
        "summary": summary,
        "link": link,
        "score": score,
        "deadline": deadline,
        "status": status,
        "giveaway_hits": giveaway_hits,
        "entry_hits": entry_hits,
        "active_hits": active_hits,
        "prop_context_hits": prop_context_hits,
    }


# ============================================================
# CANDIDATE MESSAGE
# ============================================================

def format_candidate(item):
    deadline = item["deadline"] or "Not detected"

    return (
        "🔎 PROP-FIRM DISCOVERY\n\n"
        f"🏢 Firm: {item['firm']}\n\n"
        f"🎁 {item['title']}\n\n"
        f"⭐ Score: {item['score']}/100\n"
        f"📅 Deadline: {deadline}\n\n"
        f"📝 {item['summary'][:600]}\n\n"
        f"🔗 SOURCE:\n{item['link']}"
    )


# ============================================================
# ALERT MESSAGE
# ============================================================

def format_alert(item):
    deadline = item["deadline"] or "Not detected"

    return (
        "🚨 ACTIVE PROP-FIRM GIVEAWAY\n\n"
        f"🏢 Firm: {item['firm']}\n\n"
        f"🎁 {item['title']}\n\n"
        f"⭐ Confidence: {item['score']}/100\n"
        f"📅 Deadline: {deadline}\n\n"
        f"📝 {item['summary'][:700]}\n\n"
        f"🔗 ENTER / SOURCE:\n{item['link']}"
    )


# ============================================================
# STATUS MESSAGE
# ============================================================

def format_status(
    result_count,
    candidates,
    alerts,
):
    return (
        "🔎 PROP-FIRM GIVEAWAY HUNTER\n\n"
        "Scan completed successfully.\n\n"
        f"📰 Results scanned: {result_count}\n"
        f"🎯 Candidates discovered: {len(candidates)}\n"
        f"🚨 New alerts: {alerts}\n\n"
        f"🔎 Discovery threshold: "
        f"{DISCOVERY_THRESHOLD}/100\n"
        f"🚨 Alert threshold: "
        f"{ALERT_THRESHOLD}/100"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("PROP-FIRM GIVEAWAY HUNTER V4")
    print("=" * 60)

    seen = load_seen()

    candidates = {}
    results_scanned = 0

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    for query in SEARCHES:

        print(f'Searching: "{query}"')

        feed = google_news(query)

        if not feed:
            continue

        entries = feed.entries[:MAX_RESULTS_PER_QUERY]

        for entry in entries:

            title = clean(
                entry.get("title", "")
            )

            summary = clean(
                entry.get("summary", "")
            )

            link = entry.get(
                "link",
                "",
            )

            if not title or not link:
                continue

            results_scanned += 1

            # ------------------------------------------------
            # Recent filter
            # ------------------------------------------------

            if not recent_entry(entry):
                continue

            # ------------------------------------------------
            # Unique ID
            # ------------------------------------------------

            uid = make_id(
                title,
                link,
            )

            # ------------------------------------------------
            # Analyse
            # ------------------------------------------------

            item = analyse_entry(
                title,
                summary,
                link,
            )

            if not item:
                continue

            # ------------------------------------------------
            # Keep highest-scoring duplicate
            # ------------------------------------------------

            if (
                uid not in candidates
                or item["score"]
                > candidates[uid]["score"]
            ):
                item["uid"] = uid
                candidates[uid] = item

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    candidate_list = sorted(
        candidates.values(),
        key=lambda x: x["score"],
        reverse=True,
    )

    print()
    print("=" * 60)
    print(f"RESULTS SCANNED: {results_scanned}")
    print(f"CANDIDATES: {len(candidate_list)}")
    print("=" * 60)

    # --------------------------------------------------------
    # Print every candidate for diagnostics
    # --------------------------------------------------------

    for item in candidate_list[:MAX_DISCOVERY_REPORT]:

        print(
            f"{item['score']:3}/100 | "
            f"{item['firm']} | "
            f"{item['title']}"
        )

    # --------------------------------------------------------
    # Telegram alerts
    # --------------------------------------------------------

    new_alerts = 0

    for item in candidate_list:

        uid = item["uid"]

        # Already processed
        if uid in seen:
            continue

        # ----------------------------------------------------
        # ALERT
        # ----------------------------------------------------

        if item["score"] >= ALERT_THRESHOLD:

            try:

                send_telegram(
                    format_alert(item)
                )

                print(
                    f"TELEGRAM ALERT | "
                    f"{item['firm']} | "
                    f"{item['score']}/100"
                )

                new_alerts += 1

            except Exception as e:

                print(
                    "Telegram alert error:",
                    e,
                )

        # ----------------------------------------------------
        # Mark processed
        # ----------------------------------------------------

        seen.add(uid)

    # --------------------------------------------------------
    # Save seen database
    # --------------------------------------------------------

    save_seen(seen)

    # --------------------------------------------------------
    # Telegram status
    # --------------------------------------------------------

    try:

        status_message = format_status(
            results_scanned,
            candidate_list,
            new_alerts,
        )

        send_telegram(
            status_message
        )

        print(
            "TELEGRAM STATUS SENT"
        )

    except Exception as e:

        print(
            "Telegram status error:",
            e,
        )

    # --------------------------------------------------------
    # Discovery report
    # --------------------------------------------------------

    discovery_candidates = [
        x
        for x in candidate_list
        if x["score"] >= DISCOVERY_THRESHOLD
    ]

    if discovery_candidates:

        print()
        print(
            f"DISCOVERY CANDIDATES: "
            f"{len(discovery_candidates)}"
        )

        for item in discovery_candidates[
            :MAX_DISCOVERY_REPORT
        ]:

            print(
                f"  {item['score']}/100 | "
                f"{item['firm']} | "
                f"{item['title']}"
            )

    else:

        print()
        print(
            "No candidates above discovery threshold."
        )

    print()
    print("=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
