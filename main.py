import os
import json
import hashlib
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = "seen.json"
MAX_AGE_DAYS = 45

PROP_FIRMS = [
    "FXIFY",
    "The5ers",
    "E8 Markets",
    "E8",
    "FundingPips",
    "FundedNext",
    "Funded Trading Plus",
    "Hola Prime",
    "Funded Trading Markets",
    "Funded Firm",
    "FTUK",
    "Tradeify",
    "MyFundedFX",
    "Apex Trader Funding",
    "Topstep",
]

SEARCHES = [
    '"prop firm" giveaway',
    '"funded account" giveaway',
    '"free challenge" prop firm',
    '"free funded account" trading',
    '"prop firm" contest',
    '"funded trader" giveaway',
    '"prop firm" sweepstakes',
]

GIVEAWAY_WORDS = [
    "giveaway",
    "contest",
    "sweepstakes",
    "free challenge",
    "free funded account",
    "free account",
    "win a funded account",
    "win a challenge",
]

ENTRY_WORDS = [
    "enter",
    "entry",
    "join",
    "register",
    "sign up",
    "participate",
    "deadline",
    "ends",
    "until",
]

ACTIVE_WORDS = [
    "enter now",
    "enter today",
    "join now",
    "register now",
    "participate now",
    "open now",
    "giveaway is live",
    "giveaway ends",
    "entries are open",
    "still open",
]

BAD_WORDS = [
    "nasdaq trading",
    "live trading",
    "day trading",
    "scalping",
    "trading stream",
    "youtube",
    "webinar",
    "expo",
    "conference",
    "biden",
    "wall street",
    "market analysis",
    "technical analysis",
    "review",
    "comparison",
]


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
    return BeautifulSoup(
        text or "", "html.parser"
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

    return None


def google_news(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        return feedparser.parse(response.content)

    except Exception as e:
        print("Feed error:", e)
        return None


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

    # If date cannot be read, don't automatically reject it.
    return True


def verify_page(url):
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            },
            allow_redirects=True
        )

        if response.status_code != 200:
            return None

        text = clean(response.text)
        lower = text.lower()

        giveaway_hits = sum(
            1 for word in GIVEAWAY_WORDS
            if word in lower
        )

        entry_hits = sum(
            1 for word in ENTRY_WORDS
            if word in lower
        )

        active_hits = sum(
            1 for word in ACTIVE_WORDS
            if word in lower
        )

        # Strong evidence that this is an actual giveaway page
        if giveaway_hits == 0:
            return None

        # Must contain some entry/action language
        if entry_hits == 0:
            return None

        score = 0
        score += min(giveaway_hits * 15, 45)
        score += min(entry_hits * 8, 24)
        score += min(active_hits * 15, 30)

        if "$" in text:
            score += 5

        # Look for deadline language
        deadline = None

        for phrase in [
            "deadline",
            "ends",
            "until",
            "closing date",
            "entry closes"
        ]:
            position = lower.find(phrase)

            if position >= 0:
                deadline = text[position:position + 150]
                break

        return {
            "score": min(score, 100),
            "text": text,
            "deadline": deadline,
            "url": response.url
        }

    except Exception as e:
        print("Verification error:", e)
        return None


def send_telegram(message):
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
        timeout=20
    )

    response.raise_for_status()


def main():

    seen = load_seen()
    candidates = {}

    for query in SEARCHES:

        print(f"Searching: {query}")

        feed = google_news(query)

        if not feed:
            continue

        for entry in feed.entries:

            title = clean(entry.get("title", ""))
            summary = clean(entry.get("summary", ""))
            link = entry.get("link", "")

            if not title or not link:
                continue

            if not recent_entry(entry):
                print(f"OLD | {title}")
                continue

            combined = f"{title} {summary}"

            firm = identify_firm(combined)

            if not firm:
                print(f"NO FIRM | {title}")
                continue

            uid = make_id(title, link)

            if uid in seen:
                continue

            # Reject obvious noise
            lower = combined.lower()

            if any(word in lower for word in BAD_WORDS):
                print(f"NOISE | {title}")
                continue

            print(f"VERIFY | {firm} | {title}")

            verification = verify_page(link)

            if not verification:
                print(f"REJECTED | {title}")
                continue

            final_score = verification["score"]

            if final_score < 60:
                print(
                    f"LOW SCORE {final_score} | {title}"
                )
                continue

            candidates[uid] = {
                "firm": firm,
                "title": title,
                "summary": summary[:500],
                "link": verification["url"],
                "score": final_score,
                "deadline": verification["deadline"],
            }

    print(
        f"\nACTIVE GIVEAWAYS FOUND: "
        f"{len(candidates)}"
    )

    for uid, item in candidates.items():

        deadline = item["deadline"]

        if deadline:
            deadline_text = deadline
        else:
            deadline_text = "Not detected"

        message = (
            "🚨 ACTIVE PROP-FIRM GIVEAWAY\n\n"
            f"🏢 Firm: {item['firm']}\n\n"
            f"🎁 {item['title']}\n\n"
            f"⭐ Confidence: {item['score']}/100\n\n"
            f"📅 Deadline: {deadline_text}\n\n"
            f"📝 {item['summary']}\n\n"
            f"🔗 ENTER / SOURCE:\n{item['link']}"
        )

        try:
            send_telegram(message)

            print(
                f"TELEGRAM SENT | "
                f"{item['firm']}"
            )

            seen.add(uid)

        except Exception as e:
            print("Telegram error:", e)

    save_seen(seen)


if __name__ == "__main__":
    main()
