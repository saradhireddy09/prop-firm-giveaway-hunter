import os
import re
import json
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

DISCOVERY_THRESHOLD = int(os.getenv("DISCOVERY_SCORE", "50"))
ALERT_THRESHOLD = int(os.getenv("MIN_SCORE", "70"))

MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "30"))

SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    )
}


# ============================================================
# SEARCHES
# ============================================================

GENERIC_SEARCHES = [
    '"prop firm" giveaway',
    '"prop firm" contest',
    '"prop firm" competition',
    '"prop trading" giveaway',
    '"prop trading" contest',
    '"funded account" giveaway',
    '"funded account" contest',
    '"funded trader" giveaway',
    '"free prop firm" challenge',
    '"free funded account" challenge',
    '"trading challenge" giveaway',
    '"prop firm" sweepstakes',
    '"trading account" giveaway',
    '"free trading challenge"',
]


FIRM_SEARCHES = [
    '"FTMO" giveaway',
    '"FundedNext" giveaway',
    '"The5ers" giveaway',
    '"FundingPips" giveaway',
    '"E8 Markets" giveaway',
    '"Tradeify" giveaway',
    '"Funded Trading Plus" giveaway',
    '"FXIFY" giveaway',
    '"Funded Trader Markets" giveaway',
    '"Hola Prime" giveaway',
    '"FundedFirm" giveaway',
    '"Apex Trader Funding" giveaway',
    '"Topstep" giveaway',
    '"Blue Guardian" giveaway',
    '"Alpha Capital Group" giveaway',
    '"The Funded Trader" giveaway',
    '"Goat Funded Trader" giveaway',
    '"OneUp Trader" giveaway',
    '"Bulenox" giveaway',
]


SEARCHES = GENERIC_SEARCHES + FIRM_SEARCHES


# ============================================================
# PROP FIRMS
# ============================================================

PROP_FIRMS = [
    "FTMO",
    "FundedNext",
    "The5ers",
    "FundingPips",
    "E8 Markets",
    "E8",
    "Tradeify",
    "Funded Trading Plus",
    "FXIFY",
    "Funded Trader Markets",
    "Hola Prime",
    "FundedFirm",
    "Apex Trader Funding",
    "Topstep",
    "Blue Guardian",
    "Alpha Capital Group",
    "The Funded Trader",
    "Goat Funded Trader",
    "OneUp Trader",
    "Bulenox",
    "Finotive Funding",
    "Funding Traders",
    "Ment Funding",
    "DNA Funded",
    "Lux Trading Firm",
    "Instant Funding",
]


# ============================================================
# KEYWORDS
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
    "free trading account",
]


ENTRY_WORDS = [
    "enter",
    "entry",
    "join",
    "register",
    "registration",
    "participate",
    "sign up",
    "signup",
    "follow",
    "like",
    "comment",
    "share",
    "tag",
    "retweet",
    "repost",
    "competition",
    "contest",
]


ACTIVE_WORDS = [
    "open now",
    "ongoing",
    "active",
    "currently",
    "enter now",
    "entries open",
    "registration open",
    "register now",
    "join now",
    "deadline",
    "ends",
    "ending",
    "until",
    "closes",
    "closing",
    "last chance",
]


EXPIRED_WORDS = [
    "ended",
    "has ended",
    "previous giveaway",
    "past giveaway",
    "old giveaway",
    "historical giveaway",
]


NON_PROP_WORDS = [
    "casino",
    "betting",
    "nft",
    "token airdrop",
    "crypto airdrop",
    "lottery",
]


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID missing")

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
        raise RuntimeError(str(data))


# ============================================================
# GOOGLE NEWS
# ============================================================

def google_news(query):

    try:

        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}"
            "&hl=en-US&gl=US&ceid=US:en"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

        return feedparser.parse(response.content)

    except Exception as e:

        print("FEED ERROR:", e)

        return None


# ============================================================
# CLEAN TEXT
# ============================================================

def clean(text):

    if not text:
        return ""

    soup = BeautifulSoup(
        text,
        "html.parser"
    )

    return soup.get_text(
        " ",
        strip=True
    )


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_article(url):

    if not url:
        return ""

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Remove unnecessary sections.
        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "form",
            "aside",
        ]):
            tag.decompose()

        text = soup.get_text(
            " ",
            strip=True
        )

        return text[:15000]

    except Exception:

        return ""


# ============================================================
# RECENCY
# ============================================================

def is_recent(entry):

    try:

        if hasattr(entry, "published_parsed"):

            published = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

            age = (
                datetime.now(timezone.utc)
                - published
            )

            return age <= timedelta(
                days=MAX_AGE_DAYS
            )

    except Exception:
        pass

    return True


# ============================================================
# FIRM IDENTIFICATION
# ============================================================

def identify_firm(text):

    lower = text.lower()

    for firm in PROP_FIRMS:

        if firm.lower() in lower:
            return firm

    # Generic prop-firm name detection.
    patterns = [
        r"\b[A-Z][A-Za-z0-9&.-]{2,30}\s+(?:Funding|Markets|Capital)\b",
        r"\b[A-Z][A-Za-z0-9&.-]{2,30}\s+Trading\b",
        r"\b[A-Z][A-Za-z0-9&.-]{2,30}\s+Trader\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:
            return match.group(0)

    return "Unknown"


# ============================================================
# DEADLINE
# ============================================================

def extract_deadline(text):

    patterns = [

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|at|:|-)?\s*"
        r"([A-Za-z]+\s+\d{1,2}"
        r"(?:,\s*\d{4})?)",

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|at|:|-)?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"(?:deadline|ends?|ending|closes?|closing)"
        r"\s*(?:on|at|:|-)?\s*"
        r"(\d{4}-\d{2}-\d{2})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    title,
    summary,
    article,
):

    text = (
        f"{title} "
        f"{summary} "
        f"{article}"
    )

    lower = text.lower()

    score = 0

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

    firm_hits = sum(
        1
        for firm in PROP_FIRMS
        if firm.lower() in lower
    )

    prop_context = any(
        word in lower
        for word in [
            "prop firm",
            "prop trading",
            "funded account",
            "funded trader",
            "trading challenge",
            "funding firm",
        ]
    )

    # --------------------------------------------------------
    # Giveaway evidence
    # --------------------------------------------------------

    score += min(
        giveaway_hits * 15,
        30
    )

    # --------------------------------------------------------
    # Entry evidence
    # --------------------------------------------------------

    score += min(
        entry_hits * 8,
        20
    )

    # --------------------------------------------------------
    # Active evidence
    # --------------------------------------------------------

    score += min(
        active_hits * 10,
        20
    )

    # --------------------------------------------------------
    # Known firm
    # --------------------------------------------------------

    score += min(
        firm_hits * 20,
        30
    )

    # --------------------------------------------------------
    # Prop context
    # --------------------------------------------------------

    if prop_context:
        score += 10

    # --------------------------------------------------------
    # Prize / account evidence
    # --------------------------------------------------------

    if "$" in text:
        score += 5

    if "funded" in lower:
        score += 5

    if "account" in lower:
        score += 5

    if "free" in lower:
        score += 5

    # --------------------------------------------------------
    # Penalties
    # --------------------------------------------------------

    for word in NON_PROP_WORDS:

        if word in lower:
            score -= 30

    for word in EXPIRED_WORDS:

        if word in lower:
            score -= 45

    return max(
        0,
        min(score, 100)
    )


# ============================================================
# CANDIDATE ANALYSIS
# ============================================================

def analyse_entry(entry):

    title = clean(
        entry.get("title", "")
    )

    summary = clean(
        entry.get("summary", "")
    )

    link = entry.get(
        "link",
        ""
    ).strip()

    if not title:
        return None

    if not is_recent(entry):
        return None

    # --------------------------------------------------------
    # IMPORTANT:
    # Do NOT reject here just because the RSS title
    # doesn't contain "giveaway".
    #
    # Fetch article and inspect the full content.
    # --------------------------------------------------------

    article = fetch_article(link)

    combined = (
        f"{title} "
        f"{summary} "
        f"{article}"
    )

    lower = combined.lower()

    giveaway_hits = sum(
        1
        for word in GIVEAWAY_WORDS
        if word in lower
    )

    prop_context = any(
        word in lower
        for word in [
            "prop firm",
            "prop trading",
            "funded account",
            "funded trader",
            "trading challenge",
            "funding firm",
        ]
    )

    known_firm = any(
        firm.lower() in lower
        for firm in PROP_FIRMS
    )

    # Broad discovery rule.
    if giveaway_hits == 0:
        return None

    if not prop_context and not known_firm:
        return None

    score = calculate_score(
        title,
        summary,
        article,
    )

    if score < DISCOVERY_THRESHOLD:
        return None

    firm = identify_firm(
        combined
    )

    deadline = extract_deadline(
        combined
    )

    # Prefer article text when available.
    description = (
        article
        if article
        else summary
    )

    description = description[:1800]

    return {
        "firm": firm,
        "title": title,
        "summary": description,
        "link": link,
        "score": score,
        "deadline": deadline,
    }


# ============================================================
# UNIQUE ID
# ============================================================

def make_id(title, link):

    raw = (
        f"{title}|{link}"
        .encode("utf-8")
    )

    return hashlib.sha256(
        raw
    ).hexdigest()


# ============================================================
# SEEN
# ============================================================

def load_seen():

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(
                json.load(f)
            )

    except Exception:

        return set()


def save_seen(seen):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            list(seen)[-5000:],
            f,
            indent=2
        )


# ============================================================
# ALERT FORMAT
# ============================================================

def format_alert(item):

    deadline = (
        item["deadline"]
        or "Not detected"
    )

    return (
        "🚨 ACTIVE PROP-FIRM GIVEAWAY\n\n"

        f"🏢 Firm: {item['firm']}\n\n"

        f"🎁 {item['title']}\n\n"

        f"⭐ Confidence: "
        f"{item['score']}/100\n\n"

        f"📅 Deadline: "
        f"{deadline}\n\n"

        f"📝 {item['summary']}\n\n"

        f"🔗 ENTER / SOURCE:\n"
        f"{item['link']}"
    )


# ============================================================
# DISCOVERY REPORT
# ============================================================

def discovery_report(candidates):

    if not candidates:

        return (
            "🔎 PROP-FIRM GIVEAWAY HUNTER\n\n"
            "No candidates above discovery threshold.\n\n"
            f"Discovery: "
            f"{DISCOVERY_THRESHOLD}/100\n"
            f"Alert: "
            f"{ALERT_THRESHOLD}/100"
        )

    candidates = sorted(
        candidates,
        key=lambda x: x["score"],
        reverse=True
    )

    lines = [
        "🔎 PROP-FIRM DISCOVERY REPORT",
        "",
        f"Candidates: {len(candidates)}",
        "",
    ]

    for i, item in enumerate(
        candidates[:10],
        start=1
    ):

        lines.append(
            f"{i}. {item['score']}/100 | "
            f"{item['firm']}"
        )

        lines.append(
            item["title"][:150]
        )

        lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN SCANNER
# ============================================================

def main():

    seen = load_seen()

    candidates = {}

    raw_results = 0

    print("=" * 60)
    print("PROP-FIRM GIVEAWAY HUNTER V3")
    print("=" * 60)

    for query in SEARCHES:

        print(
            f'Searching: "{query}"'
        )

        feed = google_news(
            query
        )

        if not feed:
            continue

        for entry in feed.entries:

            raw_results += 1

            try:

                item = analyse_entry(
                    entry
                )

                if not item:
                    continue

                uid = make_id(
                    item["title"],
                    item["link"]
                )

                candidates[uid] = item

            except Exception as e:

                print(
                    "ITEM ERROR:",
                    e
                )

    candidate_list = list(
        candidates.values()
    )

    print()
    print(
        f"RESULTS SCANNED: "
        f"{raw_results}"
    )

    print(
        f"CANDIDATES DISCOVERED: "
        f"{len(candidate_list)}"
    )

    # --------------------------------------------------------
    # Send discovery report
    # --------------------------------------------------------

    try:

        send_telegram(
            discovery_report(
                candidate_list
            )
        )

    except Exception as e:

        print(
            "DISCOVERY TELEGRAM ERROR:",
            e
        )

    # --------------------------------------------------------
    # Alert >= 70
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
        f"QUALIFYING ALERTS: "
        f"{len(alerts)}"
    )

    # --------------------------------------------------------
    # Send alerts
    # --------------------------------------------------------

    for uid, item in alerts:

        try:

            send_telegram(
                format_alert(item)
            )

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
    # Final summary
    # --------------------------------------------------------

    summary = (
        "🔎 Prop-Firm Giveaway Hunter\n\n"
        "Scan completed successfully.\n\n"
        f"📰 Results scanned: "
        f"{raw_results}\n"
        f"🎯 Candidates discovered: "
        f"{len(candidate_list)}\n"
        f"🚨 New alerts: "
        f"{len(alerts)}\n\n"
        f"🔎 Discovery threshold: "
        f"{DISCOVERY_THRESHOLD}/100\n"
        f"🚨 Alert threshold: "
        f"{ALERT_THRESHOLD}/100"
    )

    try:

        send_telegram(
            summary
        )

    except Exception as e:

        print(
            "SUMMARY TELEGRAM ERROR:",
            e
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print(
            "FATAL ERROR:",
            repr(e)
        )

        try:

            send_telegram(
                "❌ PROP-FIRM GIVEAWAY HUNTER ERROR\n\n"
                f"{e}"
            )

        except Exception:
            pass

        raise
