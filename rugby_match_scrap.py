import json
import os
import time

import requests
import pandas as pd

BASE = "https://www.rugbypremierleague.in/feeds/live/"
STATIC = "https://www.rugbypremierleague.in/feeds/static/"
FIXTURE_TEMPLATE = BASE + "fixture_{series_id}.json"
MATCHCENTER_TEMPLATE = BASE + "MatchCenter_MatchID-{match_id}.json"
SQUAD_TEMPLATE = STATIC + "Squad_TeamID-{team_id}.json"

# division -> series_id used in the fixture feed (match-center & squad feeds are
# shared; their match/team IDs come from the data, so no series needed there)
DIVISIONS = {"Men": 6, "Women": 7}

session = requests.Session()


# ── STEP 1: list the completed matches for one division ────────────────────────
def get_completed_match_ids(series_id):
    url = FIXTURE_TEMPLATE.format(series_id=series_id)
    data = session.get(url, timeout=20).json()
    return [
        m["Match_ID"]
        for m in data["matches"]
        if m["event_status"] == "Match Completed"
    ]


# ── STEP 2: fetch one match's detail feed by building its URL ──────────────────
def get_match_center(match_id):
    url = MATCHCENTER_TEMPLATE.format(match_id=match_id)
    resp = session.get(url, timeout=20)
    if resp.status_code != 200:
        print(f"skip match {match_id}: HTTP {resp.status_code}")
        return None
    return resp.json()


# ── STEP 3 (match grain): one row per match ────────────────────────────────────
def extract_match_row(match_id, mc, division):
    md = mc["match_detail"]
    result = md["result"]
    venue = md["venue"]
    officials = md["officials"]
    series = md["series"]

    # teams carry the per-side score + home/away flag
    teams = mc["teams"]["team"]
    home = next((t for t in teams if t["is_home_team"]), teams[0])
    away = next((t for t in teams if t is not home), teams[1])

    referee = ", ".join(o["name"] for o in officials if o["name"])
    potm = md["player_of_the_match"]
    potm_name = potm[0]["player_name"] if potm else ""

    # the feed's winning_margin is inconsistent ("-" on some matches), so
    # derive it from the two scores instead of trusting the field
    winning_margin = abs(int(home["score"]) - int(away["score"]))

    return {
        "division": division,
        "match_id": match_id,
        "match_number": md["match_number"],
        "league": series["name"],
        "stage": md["matchstage"],
        "date": md["matchdate_ist"],
        "start_time_ist": md["start_time_ist"],
        "venue": venue["name"],
        "city": venue["city"],
        "home_team": home["name"],
        "home_score": home["score"],
        "away_team": away["name"],
        "away_score": away["score"],
        "winning_team": result["winning_team"],
        "winning_margin": winning_margin,
        "result_text": result["matchresult"],
        "toss": md["toss"],
        "referee": referee,
        "player_of_the_match": potm_name,
        "status": md["matchstatus"],
    }


# ── STEP 3 (player grain): one row per player per match ────────────────────────
# These nested groups hold the per-player stats. We prefix each group's keys so
# columns stay unique and traceable (e.g. attacking_offloads vs kicking_*).
# Genuine zeros arrive as "0"; only entirely-untracked fields are null, and those
# all-null columns get dropped at the end (see main).
STAT_GROUPS = ["attacking", "defence_discipline", "kicking"]

# Most of the big "others" group is either a duplicate of the three groups above
# or untracked (null). These are the fields that live ONLY in "others" and carry
# real info, so we pull just these (prefixed "other_" to mark provenance).
OTHER_KEEP = [
    "dropped_goals", "missed_conversions", "penalty_try", "tackle_success",
    "lineouts_won", "total_lineouts", "penalty_conceded_offside",
]


def flatten_stat_groups(player):
    flat = {}
    for group in STAT_GROUPS:
        for stat, value in player[group].items():
            flat[f"{group}_{stat}"] = value
    for stat in OTHER_KEEP:
        flat[f"other_{stat}"] = player["others"].get(stat)
    return flat


# Nationality isn't in the match-center feed, so enrich from the Squad feed
# (one call per team), keyed by player_id.
def get_player_nationalities(team_ids):
    lookup = {}
    for team_id in team_ids:
        resp = session.get(SQUAD_TEMPLATE.format(team_id=team_id), timeout=20)
        if resp.status_code != 200:
            print(f"skip squad {team_id}: HTTP {resp.status_code}")
            continue
        for p in resp.json()["squads"]["squad"]["players"]:
            lookup[str(p["player_id"])] = p.get("country_name", "")
        time.sleep(0.2)
    return lookup


def extract_player_rows(match_id, mc, division):
    match_number = mc["match_detail"]["match_number"]
    rows = []
    for team in mc["teams"]["team"]:
        for player in team["squad"]:
            row = {
                "division": division,
                "match_id": match_id,
                "match_number": match_number,   # so a player's rows are traceable across matches
                "team_id": team["id"],
                "team": team["name"],
                "player_id": player["id"],
                "player_name": player["name"],
                "jersey_no": player["jersey_no"],
                "position": player["position"],
                "minutes_played": player["minutes_played"],
                "starter": player["starter"],
                "captain": player["captain"],
            }
            row.update(flatten_stat_groups(player))
            rows.append(row)
    return rows


# each division writes its own pair of CSVs ...
OUTPUT_FILES = {
    "Men":   ("rugby_matches_men.csv", "rugby_player_stats_men.csv"),
    "Women": ("rugby_matches_women.csv", "rugby_player_stats_women.csv"),
}

# ... and maps to these Google Sheet tab names (must match the sheet exactly)
SHEET_TABS = {
    "Men":   ("matches_men", "player_stats_men"),
    "Women": ("matches_women", "player_stats_women"),
}


def scrape_division(division, series_id):
    match_ids = get_completed_match_ids(series_id)
    print(f"{division}: {len(match_ids)} completed matches: {match_ids}")

    match_rows, player_rows = [], []
    for match_id in match_ids:
        mc = get_match_center(match_id)
        if mc is None:
            continue
        match_rows.append(extract_match_row(match_id, mc, division))
        player_rows.extend(extract_player_rows(match_id, mc, division))
        time.sleep(0.2)

    matches_csv, players_csv = OUTPUT_FILES[division]
    matches = pd.DataFrame(match_rows)
    matches.to_csv(matches_csv, index=False)

    players = pd.DataFrame(player_rows)
    # drop stat columns the feed never populates for anyone (all-null);
    # done dynamically so they return if a future match starts reporting them
    players = players.dropna(axis=1, how="all")

    # enrich with nationality from the Squad feed, placed next to player_name
    nationalities = get_player_nationalities(players["team_id"].unique())
    players.insert(
        players.columns.get_loc("player_name") + 1,
        "nationality",
        players["player_id"].astype(str).map(nationalities),
    )
    players.to_csv(players_csv, index=False)

    print(f"  -> {matches_csv} ({len(match_rows)} matches), "
          f"{players_csv} ({len(players)} players, {players.shape[1]} cols)\n")
    return matches, players


# ── Optional Google Sheets sync ────────────────────────────────────────────────
# Pushes each DataFrame to a named tab. Skipped silently if credentials aren't
# set, so local runs stay CSV-only. In CI these come from GitHub secrets.
def push_to_sheets(tabs):
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not (sheet_id and creds_json):
        print("Google Sheets sync skipped (GOOGLE_SHEET_ID / GOOGLE_CREDENTIALS not set)")
        return

    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    spreadsheet = gspread.authorize(creds).open_by_key(sheet_id)

    for tab_name, df in tabs.items():
        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(tab_name, rows=df.shape[0] + 10, cols=df.shape[1] + 5)
        ws.clear()
        # send everything as text; USER_ENTERED lets Sheets re-type numbers itself.
        # explicit keyword args keep this working across gspread v5/v6 (arg order changed)
        body = df.fillna("").astype(str)
        ws.update(
            range_name="A1",
            values=[body.columns.tolist()] + body.values.tolist(),
            value_input_option="USER_ENTERED",
        )
        print(f"  synced tab '{tab_name}' ({df.shape[0]} rows)")


def main():
    tabs = {}
    for division, series_id in DIVISIONS.items():
        matches, players = scrape_division(division, series_id)
        matches_tab, players_tab = SHEET_TABS[division]
        tabs[matches_tab] = matches
        tabs[players_tab] = players

    push_to_sheets(tabs)


if __name__ == "__main__":
    main()
