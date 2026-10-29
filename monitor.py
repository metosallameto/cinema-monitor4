import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://tanta.galaxy-cinema.com/"
PAGES = {
    "home": BASE,
    "coming_soon": urljoin(BASE, "next_releasing"),
}
TARGET = "avengers doomsday"
STATE_FILE = Path("state.json")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def normalize(text):
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(
        c for c in text if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

def notify(message):
    response = session.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message},
        timeout=20,
    )
    response.raise_for_status()

def inspect_page(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        title = heading.get_text(" ", strip=True)

        if TARGET not in normalize(title):
            continue

        detail_url = None
        booking_url = None
        parent = heading

        # Look near the title, not across the whole page.
        for _ in range(5):
            if parent.parent is None:
                break
            parent = parent.parent

            for link in parent.find_all("a", href=True):
                href = urljoin(url, link["href"])
                label = normalize(link.get_text(" ", strip=True))
                href_lower = href.lower()

                if label in ("book now", "book tickets"):
                    booking_url = href

                elif (
                    "movie-details/" in href_lower
                    and detail_url is None
                ):
                    detail_url = href

            if detail_url or booking_url:
                break

        # The heading itself proves the movie was found.
        return {
            "title": title,
            "detail_url": detail_url or url,
            "booking_url": booking_url,
        }

    return None

state = {
    "appearance_sent": False,
    "booking_sent": False,
}

if STATE_FILE.exists():
    try:
        saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            state.update(saved)
    except (OSError, json.JSONDecodeError):
        print("Could not read state.json; using default state.")

# Check Coming Soon first, then the homepage.
results = {}

for page_name, page_url in PAGES.items():
    try:
        results[page_name] = inspect_page(page_url)
        print(
            f"{page_name}: "
            + ("movie found" if results[page_name] else "movie not found")
        )
    except requests.RequestException as error:
        print(f"Could not check {page_name}: {error}")
        raise

found = results["coming_soon"] or results["home"]

# Alert 1: the movie appears on either monitored page.
if found and not state["appearance_sent"]:
    notify(
        "Avengers: Doomsday ظهر على Galaxy Cinema Tanta.\n"
        "صفحة الفيلم أو الصفحة التي ظهر فيها:\n"
        + found["detail_url"]
    )
    state["appearance_sent"] = True
    print("Appearance alert sent.")

# Alert 2: a Book Now / Book Tickets link is found near its title.
booking = next(
    (
        result["booking_url"]
        for result in results.values()
        if result and result["booking_url"]
    ),
    None,
)

if booking and not state["booking_sent"]:
    notify(
        "ظهر رابط Book Now لفيلم Avengers: Doomsday "
        "على Galaxy Cinema Tanta.\n"
        "تحقق من إتاحة الحجز:\n"
        + booking
    )
    state["booking_sent"] = True
    print("Booking alert sent.")

STATE_FILE.write_text(
    json.dumps(state, indent=2),
    encoding="utf-8",
)

print("Monitoring check completed.")
    
