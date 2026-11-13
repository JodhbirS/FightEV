import requests
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from database import SessionLocal
from models import Fighter

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
WIKI_HEADERS = {'User-Agent': 'FightEV-Bot/1.0 (https://fightev.app; dev@fightev.app)'}


def get_db_fighter_names() -> dict[str, str]:
    """Retrieve all known UFC fighter names from the database for fuzzy and canonical matching."""
    try:
        db = SessionLocal()
        fighters = db.query(Fighter).all()
        names = {f.name.lower(): f.name for f in fighters}
        db.close()
        return names
    except Exception as e:
        print(f"Warning: Could not query database for fighter names: {e}")
        return {}


def normalize_name(s: str) -> str:
    """Normalize names for robust matching (removes accents, punctuation, and extra whitespace)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = re.sub(r'[^a-zA-Z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def names_match(n1: str, n2: str) -> bool:
    """
    Check if two fighter names refer to the same person.
    Handles differences in name order (e.g. Xiao Long vs Long Xiao),
    suffixes (e.g. Jr.), accents, and abbreviations.
    """
    if not n1 or not n2:
        return False
    norm1 = normalize_name(n1)
    norm2 = normalize_name(n2)
    if norm1 == norm2 or norm1 in norm2 or norm2 in norm1:
        return True

    words1 = [w for w in norm1.split() if w not in ('jr', 'sr', 'ii', 'iii')]
    words2 = [w for w in norm2.split() if w not in ('jr', 'sr', 'ii', 'iii')]

    if set(words1) == set(words2):
        return True

    # Last name + first name match
    if len(words1) >= 2 and len(words2) >= 2:
        if (words1[0] in words2 and words1[-1] in words2) or (words2[0] in words1 and words2[-1] in words1):
            return True
        if words1[-1] == words2[-1] and (words1[0] in words2[0] or words2[0] in words1[0]):
            return True

    return False


def get_canonical_db_name(name: str, db_fighters: dict[str, str]) -> str:
    """Match a scraped name to the canonical database fighter name if available."""
    if not db_fighters:
        return name
    if name.lower() in db_fighters:
        return db_fighters[name.lower()]

    norm_target = normalize_name(name)
    for db_lower, canonical in db_fighters.items():
        if normalize_name(db_lower) == norm_target or names_match(name, canonical):
            return canonical

    return name


def parse_wikipedia_bouts(page_title: str) -> list[tuple[str, str]]:
    """
    Parse official bout order from a Wikipedia UFC event article.
    Returns list of (fighter1, fighter2) tuples in Main Card -> Prelims order.
    """
    try:
        parse_url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text',
            'format': 'json',
        }
        res = requests.get(parse_url, params=params, headers=WIKI_HEADERS, timeout=10)
        if res.status_code != 200:
            return []

        pdata = res.json()
        html = pdata.get('parse', {}).get('text', {}).get('*', '')
        soup = BeautifulSoup(html, 'html.parser')

        tables = soup.find_all('table', {'class': 'toccolours'}) + soup.find_all('table', {'class': 'wikitable'})
        ordered_bouts = []
        for t in tables:
            for tr in t.find_all('tr'):
                tds = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if len(tds) >= 4 and any(sep in tds[2].lower() for sep in ['vs', 'def', 'vs.']):
                    fighter_a = re.sub(r'\(.*?\)|\[.*?\]', '', tds[1]).strip()
                    fighter_b = re.sub(r'\(.*?\)|\[.*?\]', '', tds[3]).strip()
                    if (
                        fighter_a
                        and fighter_b
                        and fighter_a.lower() not in ('fighter', 'fighter 1', 'weight class', 'tba', 'tbd')
                        and fighter_b.lower() not in ('fighter', 'fighter 2', 'weight class', 'tba', 'tbd')
                    ):
                        ordered_bouts.append((fighter_a, fighter_b))

        print(f"Extracted {len(ordered_bouts)} official bouts from '{page_title}'.")
        return ordered_bouts
    except Exception as e:
        print(f"Warning: Failed to parse bouts from Wikipedia page '{page_title}': {e}")
        return []


def search_wikipedia_for_event(fighter_pairs: list[tuple[str, str]]) -> str | None:
    """Fallback search on Wikipedia using top headliner pairings."""
    search_terms = []
    for f1, f2 in fighter_pairs:
        search_terms.extend([
            f"UFC Fight Night {f1} vs {f2}",
            f"UFC Fight Night {f2} vs {f1}",
            f"UFC {f1} vs {f2}",
            f"UFC {f2} vs {f1}",
        ])

    for term in search_terms:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': term,
            'format': 'json',
        }
        try:
            res = requests.get(search_url, params=params, headers=WIKI_HEADERS, timeout=8)
            if res.status_code == 200:
                data = res.json()
                results = [
                    x['title']
                    for x in data.get('query', {}).get('search', [])
                    if 'UFC' in x['title'] and 'rankings' not in x['title'].lower() and 'list' not in x['title'].lower()
                ]
                if results:
                    return results[0]
        except Exception:
            continue
    return None


def fetch_fanduel_ufc_card():
    if not API_KEY:
        raise RuntimeError("ODDS_API_KEY is not set")

    base_url = "https://api.the-odds-api.com/v4"
    sport = "mma_mixed_martial_arts"
    db_fighters = get_db_fighter_names()
    if not db_fighters:
        raise RuntimeError("No fighters were loaded from the UFC database")

    now = datetime.now(timezone.utc)
    events_response = requests.get(
        f"{base_url}/sports/{sport}/events",
        params={
            "apiKey": API_KEY,
            "dateFormat": "iso",
            "commenceTimeFrom": (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commenceTimeTo": (now + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        timeout=15,
    )
    events_response.raise_for_status()
    events = events_response.json()
    if not events:
        raise RuntimeError("The Odds API returned no upcoming MMA events")

    parsed = []
    for event in events:
        first = event.get("home_team", "")
        second = event.get("away_team", "")
        try:
            event_time = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        verified_count = sum(
            any(names_match(name, known) for known in db_fighters.values())
            for name in (first, second)
        )
        parsed.append({
            "event": event,
            "first": first,
            "second": second,
            "time": event_time,
            "verified_count": verified_count,
        })

    parsed.sort(key=lambda item: item["time"])
    clusters: list[list[dict]] = []
    for item in parsed:
        if not clusters or (item["time"] - clusters[-1][-1]["time"]) > timedelta(hours=7):
            clusters.append([item])
        else:
            clusters[-1].append(item)

    target = max(
        clusters,
        key=lambda cluster: (sum(item["verified_count"] for item in cluster), len(cluster)),
        default=[],
    )
    if sum(item["verified_count"] for item in target) < 4:
        raise RuntimeError("Could not verify an upcoming UFC card from MMA events")

    candidate_pairs = [(item["first"], item["second"]) for item in target]
    wiki_title = search_wikipedia_for_event(candidate_pairs[:5])
    official_bouts = parse_wikipedia_bouts(wiki_title) if wiki_title else []
    if not official_bouts:
        raise RuntimeError("Could not verify the selected MMA card as a UFC event")

    def bout_rank(first: str, second: str) -> int | None:
        for index, (official_first, official_second) in enumerate(official_bouts):
            if (
                (names_match(first, official_first) and names_match(second, official_second))
                or (names_match(first, official_second) and names_match(second, official_first))
            ):
                return index
        return None

    card = []
    for item in target:
        rank = bout_rank(item["first"], item["second"])
        if rank is None:
            continue
        odds_response = requests.get(
            f"{base_url}/sports/{sport}/events/{item['event']['id']}/odds",
            params={
                "apiKey": API_KEY,
                "regions": "us",
                "markets": "h2h",
                "oddsFormat": "american",
            },
            timeout=15,
        )
        odds_response.raise_for_status()
        odds_data = odds_response.json()
        bookmaker = next(
            (book for book in odds_data.get("bookmakers", [])
             if book.get("key", "").lower() == "fanduel"),
            None,
        )
        if not bookmaker:
            continue
        market = next(
            (market for market in bookmaker.get("markets", [])
             if market.get("key") == "h2h" and len(market.get("outcomes", [])) >= 2),
            None,
        )
        if not market:
            continue
        outcomes = market["outcomes"]
        first_name, second_name = outcomes[0]["name"], outcomes[1]["name"]
        card.append({
            "fighter1": get_canonical_db_name(first_name, db_fighters),
            "fighter2": get_canonical_db_name(second_name, db_fighters),
            "odds1": outcomes[0]["price"],
            "odds2": outcomes[1]["price"],
            "_rank": rank,
        })

    if not card:
        raise RuntimeError("FanDuel returned no verified UFC fight odds")
    card.sort(key=lambda fight: fight["_rank"])
    output = [{key: value for key, value in fight.items() if not key.startswith("_")} for fight in card]

    target_path = os.path.join(os.path.dirname(__file__), "data", "card.json")
    temp_path = f"{target_path}.tmp"
    with open(temp_path, "w") as card_file:
        json.dump(output, card_file, indent=2)
        card_file.write("\n")
    os.replace(temp_path, target_path)
    print(f"Saved {len(output)} verified UFC FanDuel fights to {target_path}")


if __name__ == "__main__":
    fetch_fanduel_ufc_card()
