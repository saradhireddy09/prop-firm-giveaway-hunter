import os
import re
import json
import hashlib
from datetime import datetime, timezone, timedelta

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MIN_SCORE = int(os.getenv("MIN_SCORE", "70"))

SEEN_FILE = "seen.json"

MAX_AGE_DAYS = 7


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCHES = [
    '"prop firm" giveaway',
    '"prop trading" giveaway',
    '"funded account" giveaway',
    '"funded trader" giveaway',
    '"free prop firm" challenge',
    '"prop firm" sweepstakes',
    '"trading challenge" giveaway',
]


# ============================================================
# PROP FIRMS
# ============================================================

PROP_FIRMS = [
    "FundedNext",
    "FundingPips",
    "The5ers",
    "E8 Markets",
    "E8",
    "Funded Trader Markets",
    "Funded Trading Plus",
    "FTMO",
    "Hola Prime",
    "Funded Firm",
    "Tradeify",
    "MyFundedFX",
    "FXIFY",
    "Topstep",
    "Axi Select",
    "Alpha Capital Group",
    "Blue Guardian",
    "Goat Funded Trader",
    "Funded Trading",
    "Instant Funding",
    "The Funded Trader",
]


# ============================================================
# POSITIVE GIVEAWAY WORDS
# ============================================================

GIVEAWAY_WORDS = [
    "giveaway",
    "give away",
    "sweepstakes",
    "contest",
    "win",
    "winner",
    "prize",
    "free account",
    "free challenge",
    "free funded account",
    "free prop account",
]


# ============================================================
# ACTIVE / ENTRY WORDS
# ============================================================

ACTIVE_WORDS = [
    "enter",
    "entry",
    "join",
    "participate",
    "register",
    "sign up",
    "signup",
    "apply",
    "claim",
    "starts",
    "open",
    "running",
    "ends",
    "deadline",
]


# ============================================================
# STRONG NEGATIVE WORDS
# ============================================================

BAD_WORDS = [
    "ended",
    "ends",
    "expired",
    "closed",
    "winner announced",
    "past giveaway",
    "old giveaway",
    "review",
    "reviewed",
    "news recap",
    "podcast",
    "youtube",
    "live stream",
    "livestream",
    "nasdaq trading",
    "nasdaq futures",
    "day trading",
    "scalping",
    "order flow",
    "price action",
    "crypto airdrop",
    "airdrop",
    "token giveaway",
    "bitcoin giveaway",
    "crypto giveaway",
    "casino",
]


# ============================================================
# HELPERS
# ============================================================

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-3000:], f)


def clean(text):
    if not text:
        return ""

    return BeautifulSoup(
        text,
        "html.parser"
    ).get_text(" ", strip=True)


def make_id(title, link):
    return hashlib.sha256(
        f"{title}|{link}".encode()
    ).hexdigest()


def identify_firm(text):
    text_lower = text.lower()

    for firm in PROP_FIRMS:
        if firm.lower() in text_lower:
            return firm

    return "Unknown"


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news(query):

    url = (
        "https://news.google.com/rss/search?"
        f"q={requests.utils.quote(query)}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            },
        )

        response.raise_for_status()

        return feedparser.parse(response.content)

    except Exception as e:
        print("Feed error:", e)
        return None


# ============================================================
# RECENT ARTICLE CHECK
# ============================================================

def recent_entry(entry):

    try:

        if hasattr(entry, "published_parsed"):

            published = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

            age = datetime.now(
                timezone.utc
            ) - published

            return age <= timedelta(
                days=MAX_AGE_DAYS
            )

    except Exception:
        pass

    # If date cannot be read, don't automatically reject it.
    return True


# ============================================================
# DEADLINE DETECTION
# ============================================================

def detect_deadline(text):

    patterns = [

        r"(?:ends?|ending|deadline|closes?)"
        r".{0,60}"
        r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",

        r"(?:ends?|ending|deadline|closes?)"
        r".{0,60}"
        r"([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?"
        r"(?:,\s*\d{4})?)",

        r"(?:until|through)"
        r".{0,40}"
        r"([A-Z][a-z]+\s+\d{1,2})",
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
# CLASSIFY GIVEAWAY
# ============================================================

def classify(entry):

    title = clean(
        entry.get("title", "")
    )

    summary = clean(
        entry.get("summary", "")
    )

    link = entry.get(
        "link",
        ""
    )

    text = (
        f"{title} {summary}"
    ).strip()

    lower = text.lower()

    # --------------------------------------------------------
    # MUST BE RECENT
    # --------------------------------------------------------

    if not recent_entry(entry):
        return None

    # --------------------------------------------------------
    # MUST HAVE GIVEAWAY EVIDENCE
    # --------------------------------------------------------

    giveaway_hits = sum(
        1
        for word in GIVEAWAY_WORDS
        if word in lower
    )

    if giveaway_hits == 0:
        return None

    # --------------------------------------------------------
    # MUST HAVE ENTRY / ACTION LANGUAGE
    # --------------------------------------------------------

    entry_hits = sum(
        1
        for word in ACTIVE_WORDS
        if word in lower
    )

    if entry_hits == 0:
        return None

    # --------------------------------------------------------
    # REJECT IRRELEVANT CONTENT
    # --------------------------------------------------------

    bad_hits = sum(
        1
        for word in BAD_WORDS
        if word in lower
    )

    if bad_hits >= 2:
        return None

    # Strong rejection for obvious unrelated content
    if (
        "nasdaq" in lower
        and "prop firm" not in lower
    ):
        return None

    if (
        "crypto airdrop" in lower
        or "token giveaway" in lower
    ):
        return None

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = 0

    # Giveaway evidence
    score += min(
        giveaway_hits * 20,
        40
    )

    # Entry/action evidence
    score += min(
        entry_hits * 8,
        24
    )

    # Identifiable prop firm
    firm = identify_firm(text)

    if firm != "Unknown":
        score += 20

    # Dollar / account value
    if "$" in text:
        score += 5

    # Funded-account evidence
    funded_words = [
        "funded account",
        "funded account giveaway",
        "prop firm account",
        "trading account",
        "challenge account",
        "evaluation account",
    ]

    if any(
        word in lower
        for word in funded_words
    ):
        score += 10

    # Deadline is strong evidence
    deadline = detect_deadline(text)

    if deadline:
        score += 10

    # --------------------------------------------------------
    # CAP SCORE
    # --------------------------------------------------------

    score = min(score, 100)

    # --------------------------------------------------------
    # MINIMUM SCORE
    # --------------------------------------------------------

    if score < MIN_SCORE:
        return None

    return {
        "firm": firm,
        "title": title,
        "summary": summary[:700],
        "link": link,
        "score": score,
        "deadline": deadline,
    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing"
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID is missing"
        )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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


# ============================================================
# MAIN SCANNER
# ============================================================

def main():

    seen = load_seen()

    candidates = {}

    for query in SEARCHES:

        print(
            f'Searching: "{query}"'
        )

        feed = google_news(query)

        if not feed:
            continue

        for entry in feed.entries:

            title = clean(
                entry.get("title", "")
            )

            link = entry.get(
                "link",
                ""
            )

            uid = make_id(
                title,
                link
            )

            if uid in seen:
                continue

            item = classify(entry)

            if not item:
                continue

            # Keep the highest scoring result
            # for the same article.
            candidates[uid] = item

    print(
        f"QUALIFYING GIVEAWAYS: "
        f"{len(candidates)}"
    )

    # ========================================================
    # SEND ALERTS
    # ========================================================

    if not candidates:

        print(
            "No qualifying giveaways found."
        )

        # Optional diagnostic message.
        # This confirms the scanner is alive.
        send_telegram(
            "🔎 Prop-Firm Giveaway Hunter\n\n"
            "Scan completed successfully.\n"
            "No qualifying active prop-firm "
            "giveaways found.\n\n"
            f"Minimum score: {MIN_SCORE}/100"
        )

    else:

        for uid, item in candidates.items():

            deadline = (
                item["deadline"]
                if item["deadline"]
                else "Not detected"
            )

            message = (
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

            try:

                send_telegram(
                    message
                )

                print(
                    f"TELEGRAM SENT | "
                    f"{item['firm']} | "
                    f"{item['score']}/100"
                )

                seen.add(uid)

            except Exception as e:

                print(
                    "Telegram error:",
                    e
                )

    save_seen(seen)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
