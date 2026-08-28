import requests
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone, timedelta
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


def get_upcoming_ufc_event_page() -> str | None:
    """
    Query Wikipedia's 'List of UFC events' table to find the immediate next upcoming UFC event.
    """
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'parse',
            'page': 'List of UFC events',
            'prop': 'text',
            'format': 'json',
        }
        res = requests.get(url, params=params, headers=WIKI_HEADERS, timeout=10)
        if res.status_code != 200:
            return None
        data = res.json()
        html = data.get('parse', {}).get('text', {}).get('*', '')
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table', {'class': 'wikitable'})
        if not tables:
            return None

        upcoming_table = tables[0]
        upcoming_events = []
        for tr in upcoming_table.find_all('tr'):
            tds = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if len(tds) >= 2 and tds[0] != 'Event':
                # Remove references like [24]
                event_name = re.sub(r'\[.*?\]', '', tds[0]).strip()
                event_date = re.sub(r'\[.*?\]', '', tds[1]).strip()
                if event_name:
                    upcoming_events.append((event_name, event_date))

        if upcoming_events:
            # The upcoming table is listed chronologically reverse (farthest first, next immediate last)
            next_event_title = upcoming_events[-1][0]
            next_event_date = upcoming_events[-1][1]
            print(f"Discovered next upcoming UFC event on Wikipedia: '{next_event_title}' ({next_event_date})")
            return next_event_title

        return None
    except Exception as e:
        print(f"Warning: Could not fetch upcoming UFC events from Wikipedia: {e}")
        return None


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


def fetch_ufc_odds():
    if not API_KEY:
        print("API key not set. Please set the ODDS_API_KEY environment variable.")
        return

    base_url = "https://api.the-odds-api.com/v4"
    sport = "mma_mixed_martial_arts"
    preferred_books = ['fanduel', 'draftkings', 'betmgm', 'bovada', 'betonlineag', 'williamhill_us']

    try:
        db_fighters = get_db_fighter_names()
        print(f"Loaded {len(db_fighters)} fighters from database for verification.")

        # 1. First, find official upcoming UFC card from Wikipedia
        page_title = get_upcoming_ufc_event_page()
        official_bouts = []
        if page_title:
            official_bouts = parse_wikipedia_bouts(page_title)

        # 2. Fetch live odds for all MMA events from Odds API
        odds_url = f"{base_url}/sports/{sport}/odds"
        odds_params = {
            'apiKey': API_KEY,
            'regions': 'us',
            'markets': 'h2h',
            'oddsFormat': 'american',
        }
        print("Fetching live odds from The Odds API...")
        odds_res = requests.get(odds_url, params=odds_params, timeout=12)
        odds_res.raise_for_status()
        raw_odds_events = odds_res.json()
        print(f"Retrieved {len(raw_odds_events)} live MMA betting events.")

        # 3. If Wikipedia event page was not found or had no bouts, fallback to headliner clustering
        if not official_bouts:
            print("Fallback: Searching Wikipedia using Odds API event clusters...")
            parsed_events = []
            for event in raw_odds_events:
                f1 = event.get('home_team', '')
                f2 = event.get('away_team', '')
                commence_str = event.get('commence_time', '')
                try:
                    ctime = datetime.fromisoformat(commence_str.replace('Z', '+00:00'))
                except Exception:
                    continue

                in_db1 = f1.lower() in db_fighters or normalize_name(f1) in [normalize_name(k) for k in db_fighters]
                in_db2 = f2.lower() in db_fighters or normalize_name(f2) in [normalize_name(k) for k in db_fighters]

                parsed_events.append({
                    'event': event,
                    'f1': f1,
                    'f2': f2,
                    'ctime': ctime,
                    'is_ufc': in_db1 or in_db2,
                    'ufc_score': (1 if in_db1 else 0) + (1 if in_db2 else 0),
                })

            parsed_events.sort(key=lambda x: x['ctime'])

            # Group events into sessions
            clusters = []
            current_cluster = []
            for item in parsed_events:
                if not current_cluster:
                    current_cluster.append(item)
                else:
                    last_time = current_cluster[-1]['ctime']
                    if (item['ctime'] - last_time).total_seconds() / 3600 <= 5:
                        current_cluster.append(item)
                    else:
                        clusters.append(current_cluster)
                        current_cluster = [item]
            if current_cluster:
                clusters.append(current_cluster)

            if clusters:
                # Pick cluster with highest UFC fighter count
                best_cluster = max(clusters, key=lambda cl: sum(x['ufc_score'] for x in cl))
                search_pairs = [(x['f1'], x['f2']) for x in reversed(best_cluster)]
                found_title = search_wikipedia_for_event(search_pairs)
                if found_title:
                    print(f"Matched Wikipedia event page via Odds API cluster: '{found_title}'")
                    official_bouts = parse_wikipedia_bouts(found_title)

        # 4. Match official bouts to Odds API events to attach live moneyline odds
        card_fights = []

        if official_bouts:
            for bout_idx, (f1, f2) in enumerate(official_bouts):
                matched_event = None
                for ev in raw_odds_events:
                    home = ev.get('home_team', '')
                    away = ev.get('away_team', '')
                    if (names_match(f1, home) and names_match(f2, away)) or (names_match(f1, away) and names_match(f2, home)):
                        matched_event = ev
                        break
                    if (names_match(f1, home) or names_match(f1, away)) and (names_match(f2, home) or names_match(f2, away)):
                        matched_event = ev
                        break

                odds1, odds2 = -110, -110  # default pick'em if unlisted
                if matched_event:
                    bookmakers = {b.get('key', '').lower(): b for b in matched_event.get('bookmakers', [])}
                    chosen_bookmaker = None
                    for pref in preferred_books:
                        if pref in bookmakers:
                            chosen_bookmaker = bookmakers[pref]
                            break
                    if not chosen_bookmaker and matched_event.get('bookmakers'):
                        chosen_bookmaker = matched_event['bookmakers'][0]

                    if chosen_bookmaker:
                        for market in chosen_bookmaker.get('markets', []):
                            if market.get('key') == 'h2h' and len(market.get('outcomes', [])) >= 2:
                                outcomes = market['outcomes']
                                if names_match(f1, outcomes[0]['name']):
                                    odds1 = outcomes[0]['price']
                                    odds2 = outcomes[1]['price']
                                else:
                                    odds1 = outcomes[1]['price']
                                    odds2 = outcomes[0]['price']
                                break

                # Standardize to database canonical fighter names for accurate Elo lookup
                canonical_f1 = get_canonical_db_name(f1, db_fighters)
                canonical_f2 = get_canonical_db_name(f2, db_fighters)

                card_fights.append({
                    "fighter1": canonical_f1,
                    "fighter2": canonical_f2,
                    "odds1": odds1,
                    "odds2": odds2,
                })
        else:
            print("Error: Could not retrieve official UFC fight card.")
            return

        print(f"\nSuccessfully compiled official UFC fight card ({len(card_fights)} bouts):")
        for idx, f in enumerate(card_fights):
            print(f"  #{idx + 1:02d}: {f['fighter1']} ({f['odds1']:+d}) vs {f['fighter2']} ({f['odds2']:+d})")

        # 5. Save to backend/data/card.json and data/card.json
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        target_path = os.path.join(data_dir, "card.json")

        with open(target_path, "w") as f:
            json.dump(card_fights, f, indent=2)

        print(f"\nCard saved to {target_path}")

        # Also write to root data/ if present
        root_data_dir = os.path.join(os.path.dirname(base_dir), "data")
        if os.path.exists(root_data_dir):
            root_card_path = os.path.join(root_data_dir, "card.json")
            with open(root_card_path, "w") as f:
                json.dump(card_fights, f, indent=2)

    except Exception as e:
        print(f"Error in fetch_ufc_odds: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    fetch_ufc_odds()
