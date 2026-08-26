import requests
import json
import os
import re
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from database import SessionLocal
from models import Fighter

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
WIKI_HEADERS = {'User-Agent': 'FightEV-Bot/1.0 (https://fightev.app; dev@fightev.app)'}


def get_db_fighter_names():
    """Retrieve all known UFC fighter names from the database for matching."""
    try:
        db = SessionLocal()
        fighters = db.query(Fighter).all()
        names = {f.name.lower(): f.name for f in fighters}
        db.close()
        return names
    except Exception as e:
        print(f"Warning: Could not query database for fighter names: {e}")
        return {}


def get_wikipedia_official_card_order(fighter_pairs: list):
    """
    Search Wikipedia for the official UFC card article and parse the exact bout order.
    Returns a list of (fighter1, fighter2) tuples in official Main Event -> Prelims order.
    """
    try:
        page_title = None

        # Build candidate search queries from the top fight pairings
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
            res = requests.get(search_url, params=params, headers=WIKI_HEADERS, timeout=8)
            if res.status_code == 200:
                data = res.json()
                results = [x['title'] for x in data.get('query', {}).get('search', []) if 'UFC' in x['title'] and 'rankings' not in x['title'].lower()]
                if results:
                    page_title = results[0]
                    break

        if not page_title:
            print("No matching Wikipedia UFC event page found.")
            return []

        print(f"Matched official Wikipedia event page: '{page_title}'")
        parse_url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text',
            'format': 'json',
        }
        res = requests.get(parse_url, params=params, headers=WIKI_HEADERS, timeout=8)
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
                    if fighter_a and fighter_b and 'weight' not in fighter_a.lower() and 'fighter' not in fighter_a.lower():
                        ordered_bouts.append((fighter_a, fighter_b))

        print(f"Extracted {len(ordered_bouts)} bouts in official order from Wikipedia.")
        return ordered_bouts
    except Exception as e:
        print(f"Warning: Failed to fetch Wikipedia card order: {e}")
        return []


def normalize_name(name: str) -> str:
    """Simplify names for fuzzy matching (lowercase, alphanumeric only)."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def match_bout_rank(f1: str, f2: str, wiki_bouts: list) -> int:
    """
    Find the 0-indexed position of this matchup in the official Wikipedia card list.
    Returns rank (0 for Main Event, 1 for Co-Main, etc.), or 999 if not found.
    """
    n1 = normalize_name(f1)
    n2 = normalize_name(f2)

    for idx, (wb1, wb2) in enumerate(wiki_bouts):
        wn1 = normalize_name(wb1)
        wn2 = normalize_name(wb2)

        # Match either fighter in this bout
        match1 = (n1 in wn1 or wn1 in n1 or n1 in wn2 or wn2 in n1)
        match2 = (n2 in wn1 or wn1 in n2 or n2 in wn2 or wn2 in n2)

        if match1 and match2:
            return idx
        if match1 or match2:
            return idx

    return 999


def fetch_ufc_odds():
    if not API_KEY:
        print("API key not set. Please set the ODDS_API_KEY environment variable.")
        return

    base_url = "https://api.the-odds-api.com/v4"
    sport = "mma_mixed_martial_arts"

    try:
        db_fighters = get_db_fighter_names()
        print(f"Loaded {len(db_fighters)} fighters from database for verification.")

        # 1. Fetch upcoming MMA events
        now_utc = datetime.now(timezone.utc)
        events_url = f"{base_url}/sports/{sport}/events"
        params = {
            'apiKey': API_KEY,
            'dateFormat': 'iso',
            'commenceTimeFrom': (now_utc - timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'commenceTimeTo': (now_utc + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }

        response = requests.get(events_url, params=params)
        response.raise_for_status()
        raw_events = response.json()
        print(f"Retrieved {len(raw_events)} raw MMA events from Odds API.")

        if not raw_events:
            print("No MMA events found.")
            return

        # 2. Parse events and check UFC roster presence
        parsed_events = []
        for event in raw_events:
            f1 = event.get('home_team', '')
            f2 = event.get('away_team', '')
            commence_str = event.get('commence_time', '')
            try:
                ctime = datetime.fromisoformat(commence_str.replace('Z', '+00:00'))
            except Exception:
                continue

            in_db1 = f1.lower() in db_fighters
            in_db2 = f2.lower() in db_fighters

            parsed_events.append({
                'event': event,
                'f1': f1,
                'f2': f2,
                'ctime': ctime,
                'is_ufc': in_db1 or in_db2,
                'ufc_score': (1 if in_db1 else 0) + (1 if in_db2 else 0)
            })

        # Sort all parsed events chronologically
        parsed_events.sort(key=lambda x: x['ctime'])

        # 3. Cluster events into distinct fight sessions using a 7-hour rolling window.
        clusters = []
        current_cluster = []
        for item in parsed_events:
            if not current_cluster:
                current_cluster.append(item)
            else:
                last_time = current_cluster[-1]['ctime']
                if (item['ctime'] - last_time).total_seconds() / 3600 <= 7:
                    current_cluster.append(item)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [item]
        if current_cluster:
            clusters.append(current_cluster)

        # 4. Find the target UFC card cluster:
        target_cluster = None
        for cl in clusters:
            ufc_count = sum(1 for x in cl if x['is_ufc'])
            if ufc_count >= 4:
                target_cluster = cl
                break

        if not target_cluster and clusters:
            target_cluster = max(clusters, key=lambda cl: sum(1 for x in cl if x['is_ufc']))

        if not target_cluster:
            print("No valid UFC card cluster identified.")
            return

        ufc_fighters_in_card = sum(1 for x in target_cluster if x['is_ufc'])
        card_start = target_cluster[0]['ctime']
        card_end = target_cluster[-1]['ctime']
        print(f"Selected UFC Card: {len(target_cluster)} fights ({ufc_fighters_in_card} UFC verified) spanning {card_start} to {card_end}")

        # 5. Fetch official fight order from Wikipedia
        # Identify top fighter pairs (especially the latest scheduled fight which is typically the Main Event)
        sorted_cluster_by_time_desc = sorted(target_cluster, key=lambda x: x['ctime'], reverse=True)
        search_pairs = [(x['f1'], x['f2']) for x in sorted_cluster_by_time_desc]
        wiki_bouts = get_wikipedia_official_card_order(search_pairs)

        # 6. Fetch odds for each fight on the card
        preferred_books = ['fanduel', 'draftkings', 'betmgm', 'bovada', 'betonlineag', 'williamhill_us']

        card_fights = []
        for item in target_cluster:
            event = item['event']
            odds_url = f"{base_url}/sports/{sport}/events/{event['id']}/odds"
            odds_params = {
                'apiKey': API_KEY,
                'regions': 'us',
                'markets': 'h2h',
                'oddsFormat': 'american'
            }

            try:
                odds_response = requests.get(odds_url, params=odds_params)
                odds_response.raise_for_status()
                odds_data = odds_response.json()

                chosen_bookmaker = None
                bookmakers = {b.get('key', '').lower(): b for b in odds_data.get('bookmakers', [])}
                for pref in preferred_books:
                    if pref in bookmakers:
                        chosen_bookmaker = bookmakers[pref]
                        break

                if not chosen_bookmaker and odds_data.get('bookmakers'):
                    chosen_bookmaker = odds_data['bookmakers'][0]

                if chosen_bookmaker:
                    for market in chosen_bookmaker.get('markets', []):
                        if market['key'] == 'h2h' and len(market['outcomes']) >= 2:
                            outcomes = market['outcomes']
                            f1_name = outcomes[0]['name']
                            f2_name = outcomes[1]['name']
                            f1_odds = outcomes[0]['price']
                            f2_odds = outcomes[1]['price']

                            rank = match_bout_rank(f1_name, f2_name, wiki_bouts) if wiki_bouts else 999

                            card_fights.append({
                                "fighter1": f1_name,
                                "fighter2": f2_name,
                                "odds1": f1_odds,
                                "odds2": f2_odds,
                                "commence_time": item['ctime'].isoformat(),
                                "wiki_rank": rank
                            })
                            break
            except Exception as e:
                print(f"Error fetching odds for {item['f1']} vs {item['f2']}: {e}")
                continue

        # 7. Sort fights into official fight card order:
        # Sort by wiki_rank ascending (0 = Main Event, 1 = Co-Main, etc.)
        if wiki_bouts and any(f['wiki_rank'] < 999 for f in card_fights):
            card_fights.sort(key=lambda x: (x['wiki_rank'], -datetime.fromisoformat(x['commence_time']).timestamp()))
        else:
            card_fights.sort(key=lambda x: x.get('commence_time', ''), reverse=True)

        output_fights = []
        for f in card_fights:
            output_fights.append({
                "fighter1": f["fighter1"],
                "fighter2": f["fighter2"],
                "odds1": f["odds1"],
                "odds2": f["odds2"]
            })

        print(f"Successfully processed {len(output_fights)} UFC card fights in official order:")
        for idx, f in enumerate(output_fights):
            print(f"  #{idx + 1}: {f['fighter1']} vs {f['fighter2']}")

        # 8. Write to data/card.json
        if os.path.basename(os.getcwd()) == 'backend':
            card_file = 'data/card.json'
            os.makedirs('data', exist_ok=True)
        else:
            card_file = 'backend/data/card.json'
            os.makedirs('backend/data', exist_ok=True)

        with open(card_file, 'w') as f:
            json.dump(output_fights, f, indent=2)

        print(f"Card saved to {card_file}")

    except Exception as e:
        print(f"Error in fetch_ufc_odds: {e}")


if __name__ == "__main__":
    fetch_ufc_odds()
