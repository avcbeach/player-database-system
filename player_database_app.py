import streamlit as st
import pandas as pd
from datetime import date, timedelta
import os
import uuid
from io import BytesIO, StringIO
import requests
from base64 import b64encode, b64decode

# -------------------------
# CONFIG & CONSTANTS
# -------------------------

st.set_page_config(
    page_title="AVC Player Database",
    page_icon="🏐",
    layout="wide",
)

DATA_DIR = "data"
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.csv")
RESULTS_FILE = os.path.join(DATA_DIR, "results.csv")

PLAYER_COLUMNS = [
    "player_id",
    "first_name",
    "last_name",
    "shirt_name",   # NEW
    "gender",
    "fivb_id",
    "birth_date",
    "nationality",
    "photo_file",
]

RESULT_COLUMNS = [
    "result_id",
    "player_id",
    "season",
    "date",
    "event_type",
    "tournament_name",
    "teammate",
    "points",
    "rank",
    "prize_money",
]

EVENT_TYPES = ["AVC", "FIVB", "AVC Multi/Zonal", "Other Multi/Zonal"]

GENDER_OPTIONS = ["", "Male", "Female"]  # "" = not specified

# -------------------------
# GITHUB STORAGE CONFIG
# -------------------------

USE_GITHUB = False
GH_OWNER = GH_REPO = GH_BRANCH = GH_TOKEN = None

try:
    if "github" in st.secrets:
        gh_cfg = st.secrets["github"]
        GH_TOKEN = gh_cfg.get("token")
        GH_OWNER = gh_cfg.get("repo_owner")
        GH_REPO = gh_cfg.get("repo_name")
        GH_BRANCH = gh_cfg.get("branch", "main")
        if GH_TOKEN and GH_OWNER and GH_REPO:
            USE_GITHUB = True
except Exception:
    USE_GITHUB = False


def github_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def github_get_file(path: str):
    """Get a file from GitHub repo via contents API.
       Returns (bytes_content, sha) or (None, None) if not found/error.
    """
    if not USE_GITHUB:
        return None, None

    path = path.replace("\\", "/")
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    params = {}
    if GH_BRANCH:
        params["ref"] = GH_BRANCH

    resp = requests.get(url, headers=github_headers(), params=params)
    if resp.status_code == 200:
        data = resp.json()
        content = b64decode(data["content"])
        sha = data["sha"]
        return content, sha
    elif resp.status_code == 404:
        return None, None
    else:
        st.error(f"GitHub read error for {path}: {resp.status_code} {resp.text}")
        return None, None


def github_put_file(path: str, content_bytes: bytes, message: str):
    """Create or update a file in the GitHub repo."""
    if not USE_GITHUB:
        return

    path = path.replace("\\", "/")
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"

    # Check if file exists to get sha
    existing_content, existing_sha = github_get_file(path)
    payload = {
        "message": message,
        "content": b64encode(content_bytes).decode("utf-8"),
        "branch": GH_BRANCH or "main",
    }
    if existing_content is not None and existing_sha:
        payload["sha"] = existing_sha

    resp = requests.put(url, headers=github_headers(), json=payload)
    if resp.status_code not in (200, 201):
        st.error(f"GitHub write error for {path}: {resp.status_code} {resp.text}")


# -------------------------
# UTIL FUNCTIONS
# -------------------------

def ensure_dirs():
    """For local mode only (no effect when using GitHub)."""
    if USE_GITHUB:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)


def load_players():
    if USE_GITHUB:
        content, _ = github_get_file(PLAYERS_FILE)
        if content is None:
            df = pd.DataFrame(columns=PLAYER_COLUMNS)
        else:
            df = pd.read_csv(StringIO(content.decode("utf-8")), dtype=str)
    else:
        ensure_dirs()
        if os.path.exists(PLAYERS_FILE):
            df = pd.read_csv(PLAYERS_FILE, dtype=str)
        else:
            df = pd.DataFrame(columns=PLAYER_COLUMNS)

    # Ensure all columns exist (for old CSVs)
    for col in PLAYER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df.fillna("")
    return df


def load_results():
    if USE_GITHUB:
        content, _ = github_get_file(RESULTS_FILE)
        if content is None:
            df = pd.DataFrame(columns=RESULT_COLUMNS)
        else:
            df = pd.read_csv(StringIO(content.decode("utf-8")), dtype=str)
    else:
        ensure_dirs()
        if os.path.exists(RESULTS_FILE):
            df = pd.read_csv(RESULTS_FILE, dtype=str)
        else:
            df = pd.DataFrame(columns=RESULT_COLUMNS)

    if not df.empty:
        for col in ["points", "prize_money"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "rank" in df.columns:
            df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df


def save_players(df):
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    if USE_GITHUB:
        github_put_file(PLAYERS_FILE, csv_bytes, "Update players.csv from Streamlit app")
    else:
        ensure_dirs()
        df.to_csv(PLAYERS_FILE, index=False)


def save_results(df):
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    if USE_GITHUB:
        github_put_file(RESULTS_FILE, csv_bytes, "Update results.csv from Streamlit app")
    else:
        ensure_dirs()
        df.to_csv(RESULTS_FILE, index=False)


def new_id():
    return str(uuid.uuid4())


def player_display_name(row):
    base = f"{row['first_name']} {row['last_name']}".strip()
    if isinstance(row.get("fivb_id"), str) and row["fivb_id"].strip():
        return f"{base} (FIVB: {row['fivb_id']})"
    return base


def shirt_or_name(row):
    s = str(row.get("shirt_name", "")).strip()
    if s:
        return s
    return f"{row['first_name']} {row['last_name']}".strip()


def get_player_by_id(players_df, player_id):
    if players_df.empty:
        return None
    row = players_df[players_df["player_id"] == player_id]
    if row.empty:
        return None
    return row.iloc[0]


def calculate_player_points(results_df, player_id, mode="365", ref_date=None,
                            start_date=None, end_date=None):
    """
    mode = "365" -> last 365 days from ref_date
    mode = "custom" -> between start_date and end_date
    Returns dict with totals + selected rows.
    """
    res = results_df[results_df["player_id"] == player_id].copy()
    if res.empty:
        return {
            "total_points": 0.0,
            "bucket1_points": 0.0,
            "bucket2_points": 0.0,
            "selected_results": pd.DataFrame(columns=RESULT_COLUMNS),
            "window_results": pd.DataFrame(columns=RESULT_COLUMNS),
            "scenario": "no_results",
            "period_text": "",
        }

    res["date"] = pd.to_datetime(res["date"], errors="coerce").dt.date

    if mode == "365":
        if ref_date is None:
            ref_date = date.today()
        start = ref_date - timedelta(days=365)
        end = ref_date
        period_text = f"{start.isoformat()} → {end.isoformat()} (last 365 days)"
    else:
        start = start_date
        end = end_date
        if start is None or end is None:
            return {
                "total_points": 0.0,
                "bucket1_points": 0.0,
                "bucket2_points": 0.0,
                "selected_results": pd.DataFrame(columns=RESULT_COLUMNS),
                "window_results": pd.DataFrame(columns=RESULT_COLUMNS),
                "scenario": "invalid_period",
                "period_text": "No period selected",
            }
        period_text = f"{start.isoformat()} → {end.isoformat()}"

    window = res[(res["date"] >= start) & (res["date"] <= end)].copy()
    if window.empty:
        return {
            "total_points": 0.0,
            "bucket1_points": 0.0,
            "bucket2_points": 0.0,
            "selected_results": pd.DataFrame(columns=RESULT_COLUMNS),
            "window_results": window,
            "scenario": "no_results_in_period",
            "period_text": period_text,
        }

    window["points"] = pd.to_numeric(window["points"], errors="coerce").fillna(0.0)

    # Scenario A: allow AVC Multi/Zonal, disallow Other Multi/Zonal
    bucket1_A = window[window["event_type"].isin(["AVC", "AVC Multi/Zonal"])].copy()
    bucket2_A = window[window["event_type"] == "FIVB"].copy()

    bucket1_A_top = bucket1_A.sort_values("points", ascending=False).head(4)
    bucket2_A_top = bucket2_A.sort_values("points", ascending=False).head(4)

    bucket1_A_pts = bucket1_A_top["points"].sum()
    bucket2_A_pts = bucket2_A_top["points"].sum()
    total_A = bucket1_A_pts + bucket2_A_pts

    # Scenario B: allow Other Multi/Zonal, disallow AVC Multi/Zonal
    bucket1_B = window[window["event_type"] == "AVC"].copy()
    bucket2_B = window[window["event_type"].isin(["FIVB", "Other Multi/Zonal"])].copy()

    bucket1_B_top = bucket1_B.sort_values("points", ascending=False).head(4)
    bucket2_B_top = bucket2_B.sort_values("points", ascending=False).head(4)

    bucket1_B_pts = bucket1_B_top["points"].sum()
    bucket2_B_pts = bucket2_B_top["points"].sum()
    total_B = bucket1_B_pts + bucket2_B_pts

    if total_A >= total_B:
        selected = pd.concat([bucket1_A_top, bucket2_A_top], ignore_index=True)
        scenario = "AVC_MZ_used"
        total_points = total_A
        bucket1_points = bucket1_A_pts
        bucket2_points = bucket2_A_pts
    else:
        selected = pd.concat([bucket1_B_top, bucket2_B_top], ignore_index=True)
        scenario = "Other_MZ_used"
        total_points = total_B
        bucket1_points = bucket1_B_pts
        bucket2_points = bucket2_B_pts

    selected = selected.sort_values("points", ascending=False)

    return {
        "total_points": float(total_points),
        "bucket1_points": float(bucket1_points),
        "bucket2_points": float(bucket2_points),
        "selected_results": selected,
        "window_results": window.sort_values("date"),
        "scenario": scenario,
        "period_text": period_text,
    }


# -------------------------
# PAGE: ADD / EDIT PLAYER
# -------------------------

def page_add_edit_player():
    st.title("🏐 Player Manager – Add / Edit Players")

    players_df = load_players()
    results_df = load_results()

    st.markdown("Use this page to **create new players** or **edit existing players**.")

    if players_df.empty:
        options = ["<New Player>"]
        mapping = {}
    else:
        mapping = {
            player_display_name(row): row["player_id"]
            for _, row in players_df.sort_values(["last_name", "first_name"]).iterrows()
        }
        options = ["<New Player>"] + list(mapping.keys())

    selected_label = st.selectbox("Select player to edit", options)
    selected_player_id = mapping.get(selected_label)

    if selected_player_id:
        player_row = get_player_by_id(players_df, selected_player_id)
    else:
        player_row = None

    st.subheader("Player Information")
    with st.form("player_form"):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            first_name = st.text_input(
                "First name",
                value=player_row["first_name"] if player_row is not None else "",
            )
            last_name = st.text_input(
                "Last name",
                value=player_row["last_name"] if player_row is not None else "",
            )
        with col2:
            shirt_name = st.text_input(
                "Shirt name (short name)",
                value=player_row["shirt_name"] if player_row is not None else "",
                help="Name used on ranking lists, e.g. 'LEE J.'",
            )
            gender_default = player_row["gender"] if player_row is not None else ""
            if gender_default not in GENDER_OPTIONS:
                gender_default = ""
            gender = st.selectbox("Gender", GENDER_OPTIONS, index=GENDER_OPTIONS.index(gender_default))
        with col3:
            fivb_id = st.text_input(
                "FIVB ID",
                value=player_row["fivb_id"] if player_row is not None else "",
            )
            nationality = st.text_input(
                "Nationality (e.g. THA, CHN, JPN)",
                value=player_row["nationality"] if player_row is not None else "",
            )
        with col4:
            birth_date_str = st.text_input(
                "Birth date (YYYY-MM-DD)",
                value=player_row["birth_date"] if player_row is not None else "",
                help="Free text, but recommended format: YYYY-MM-DD",
            )
            photo_file = st.file_uploader(
                "Upload Photo ID (optional)",
                type=["png", "jpg", "jpeg"],
            )

        submitted = st.form_submit_button("💾 Save Player")

    if submitted:
        if not first_name.strip() and not last_name.strip():
            st.error("Please enter at least a first name or last name.")
            return

        # New player
        if player_row is None:
            player_id = new_id()
            photo_path = ""
            if photo_file is not None:
                ext = os.path.splitext(photo_file.name)[1]
                photo_filename = f"{player_id}{ext}"
                photo_path = f"photos/{photo_filename}"

                if USE_GITHUB:
                    github_put_file(
                        os.path.join(DATA_DIR, photo_path),
                        bytes(photo_file.getbuffer()),
                        f"Upload photo for player {player_id}",
                    )
                else:
                    ensure_dirs()
                    with open(os.path.join(DATA_DIR, photo_path), "wb") as f:
                        f.write(photo_file.getbuffer())

            new_player = pd.DataFrame(
                [{
                    "player_id": player_id,
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "shirt_name": shirt_name.strip(),
                    "gender": gender.strip(),
                    "fivb_id": fivb_id.strip(),
                    "birth_date": birth_date_str.strip(),
                    "nationality": nationality.strip(),
                    "photo_file": photo_path,
                }]
            )

            players_df = pd.concat([players_df, new_player], ignore_index=True)
            save_players(players_df)
            st.success("New player created successfully ✅")
        else:
            # Update existing player
            idx = players_df[players_df["player_id"] == player_row["player_id"]].index[0]

            photo_path = players_df.loc[idx, "photo_file"] or ""
            if photo_file is not None:
                ext = os.path.splitext(photo_file.name)[1]
                photo_filename = f"{player_row['player_id']}{ext}"
                photo_path = f"photos/{photo_filename}"

                if USE_GITHUB:
                    github_put_file(
                        os.path.join(DATA_DIR, photo_path),
                        bytes(photo_file.getbuffer()),
                        f"Upload/update photo for player {player_row['player_id']}",
                    )
                else:
                    ensure_dirs()
                    with open(os.path.join(DATA_DIR, photo_path), "wb") as f:
                        f.write(photo_file.getbuffer())

            players_df.loc[idx, "first_name"] = first_name.strip()
            players_df.loc[idx, "last_name"] = last_name.strip()
            players_df.loc[idx, "shirt_name"] = shirt_name.strip()
            players_df.loc[idx, "gender"] = gender.strip()
            players_df.loc[idx, "fivb_id"] = fivb_id.strip()
            players_df.loc[idx, "birth_date"] = birth_date_str.strip()
            players_df.loc[idx, "nationality"] = nationality.strip()
            players_df.loc[idx, "photo_file"] = photo_path

            save_players(players_df)
            st.success("Player information updated ✅")

    # Add / edit results for selected player
    if player_row is not None:
        st.markdown("---")
        st.subheader("Add Result for This Player")

        with st.form("add_result_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                season = st.text_input("Season (e.g. 2025)")
                date_value = st.date_input(
                    "Tournament date",
                    value=date.today(),
                )
            with c2:
                event_type = st.selectbox("Event type", EVENT_TYPES)
                tournament_name = st.text_input("Tournament name")
            with c3:
                # Teammate selection from existing players
                all_players = players_df.copy()
                other_players = all_players[all_players["player_id"] != player_row["player_id"]]

                teammate_options = ["(None)"] + [
                    f"{r['first_name']} {r['last_name']} (FIVB: {r['fivb_id']})"
                    for _, r in other_players.iterrows()
                ]

                teammate_label = st.selectbox("Teammate (from database)", teammate_options)

                if teammate_label == "(None)":
                    teammate = ""
                else:
                    teammate = teammate_label.split(" (FIVB")[0].strip()

                points = st.number_input("Points", min_value=0.0, step=1.0)
                prize_money = st.number_input("Prize money", min_value=0.0, step=100.0)

            rank = st.number_input("Rank", min_value=1, step=1)
            result_submit = st.form_submit_button("➕ Add Result")

        if result_submit:
            # 1) Add result for current player (A)
            new_result_A = {
                "result_id": new_id(),
                "player_id": player_row["player_id"],
                "season": str(season),
                "date": date_value,
                "event_type": event_type,
                "tournament_name": tournament_name,
                "teammate": teammate,
                "points": float(points),
                "rank": int(rank),
                "prize_money": float(prize_money),
            }

            results_df = pd.concat([results_df, pd.DataFrame([new_result_A])], ignore_index=True)

            # 2) If teammate selected, also add mirrored result for teammate (B)
            if teammate != "":
                full_name_A = f"{player_row['first_name']} {player_row['last_name']}"
                teammate_row_df = players_df[
                    (players_df["first_name"] + " " + players_df["last_name"]) == teammate
                ]
                if not teammate_row_df.empty:
                    teammate_id = teammate_row_df.iloc[0]["player_id"]
                    new_result_B = {
                        "result_id": new_id(),
                        "player_id": teammate_id,
                        "season": str(season),
                        "date": date_value,
                        "event_type": event_type,
                        "tournament_name": tournament_name,
                        "teammate": full_name_A,
                        "points": float(points),
                        "rank": int(rank),
                        "prize_money": float(prize_money),
                    }
                    results_df = pd.concat([results_df, pd.DataFrame([new_result_B])], ignore_index=True)

            save_results(results_df)
            st.success("Result added (including teammate, if selected) ✅")
            st.rerun()

        st.markdown("### Existing Results for This Player")

        player_results = results_df[results_df["player_id"] == player_row["player_id"]]

        if player_results.empty:
            st.info("No results stored yet.")
        else:
            # Display without technical IDs
            display_cols = [c for c in player_results.columns if c not in ["result_id", "player_id"]]
            player_results_sorted = player_results.sort_values("date", ascending=False).reset_index(drop=True)
            st.dataframe(player_results_sorted[display_cols], use_container_width=True)

            st.markdown("#### ✏️ Edit a Result")
            result_choices = [
                f"{r['date']} — {r['tournament_name']} ({r['event_type']})"
                for _, r in player_results_sorted.iterrows()
            ]

            selected_edit = st.selectbox("Select result to edit", ["(None)"] + result_choices)

            if selected_edit != "(None)":
                idx = result_choices.index(selected_edit)
                edit_row = player_results_sorted.iloc[idx]
                res_id = edit_row["result_id"]

                # Keep original values for mirrored update
                orig_season = edit_row["season"]
                orig_date = edit_row["date"]
                orig_event_type = edit_row["event_type"]
                orig_tournament = edit_row["tournament_name"]
                orig_teammate = edit_row["teammate"]
                orig_points = float(edit_row["points"])
                orig_rank = float(edit_row["rank"])
                orig_prize = float(edit_row["prize_money"])

                st.markdown("### Edit Result Details")
                with st.form("edit_result_form"):
                    colA, colB, colC = st.columns(3)
                    with colA:
                        season_edit = st.text_input("Season", edit_row["season"])
                        date_edit = st.date_input("Date", edit_row["date"])
                    with colB:
                        try:
                            event_index = EVENT_TYPES.index(edit_row["event_type"])
                        except ValueError:
                            event_index = 0
                        event_type_edit = st.selectbox("Event type", EVENT_TYPES, index=event_index)
                        tournament_edit = st.text_input("Tournament name", edit_row["tournament_name"])
                    with colC:
                        # Teammate dropdown for edit
                        all_players = players_df.copy()
                        other_players = all_players[all_players["player_id"] != player_row["player_id"]]

                        teammate_options2 = ["(None)"] + [
                            f"{r['first_name']} {r['last_name']} (FIVB: {r['fivb_id']})"
                            for _, r in other_players.iterrows()
                        ]

                        # Default selection
                        if not edit_row["teammate"]:
                            default_tm_index = 0
                        else:
                            default_tm_index = 0
                            for i, label in enumerate(teammate_options2):
                                if label.startswith(edit_row["teammate"]):
                                    default_tm_index = i
                                    break

                        teammate_label2 = st.selectbox("Teammate", teammate_options2, index=default_tm_index)

                        if teammate_label2 == "(None)":
                            teammate_edit = ""
                        else:
                            teammate_edit = teammate_label2.split(" (FIVB")[0].strip()

                        points_edit = st.number_input("Points", value=float(edit_row["points"]), min_value=0.0)
                        prize_edit = st.number_input("Prize money", value=float(edit_row["prize_money"]), min_value=0.0)

                    rank_edit = st.number_input("Rank", value=int(edit_row["rank"]), min_value=1)

                    submitted_edit = st.form_submit_button("💾 Save Changes")

                if submitted_edit:
                    # Update this player's result
                    mask = results_df["result_id"] == res_id
                    results_df.loc[mask, "season"] = season_edit
                    results_df.loc[mask, "date"] = date_edit
                    results_df.loc[mask, "event_type"] = event_type_edit
                    results_df.loc[mask, "tournament_name"] = tournament_edit
                    results_df.loc[mask, "teammate"] = teammate_edit
                    results_df.loc[mask, "points"] = points_edit
                    results_df.loc[mask, "rank"] = rank_edit
                    results_df.loc[mask, "prize_money"] = prize_edit

                    # Try to update teammate's mirrored result if teammate not changed
                    if orig_teammate and orig_teammate == teammate_edit:
                        tm_row = players_df[
                            (players_df["first_name"] + " " + players_df["last_name"]) == orig_teammate
                        ]
                        if not tm_row.empty:
                            tm_id = tm_row.iloc[0]["player_id"]
                            full_name_A = f"{player_row['first_name']} {player_row['last_name']}"

                            mirrored_mask = (
                                (results_df["player_id"] == tm_id) &
                                (results_df["teammate"] == full_name_A) &
                                (results_df["season"] == orig_season) &
                                (pd.to_datetime(results_df["date"], errors="coerce").dt.date == orig_date) &
                                (results_df["event_type"] == orig_event_type) &
                                (results_df["tournament_name"] == orig_tournament) &
                                (pd.to_numeric(results_df["points"], errors="coerce") == orig_points) &
                                (pd.to_numeric(results_df["rank"], errors="coerce") == orig_rank) &
                                (pd.to_numeric(results_df["prize_money"], errors="coerce") == orig_prize)
                            )

                            if mirrored_mask.any():
                                results_df.loc[mirrored_mask, "season"] = season_edit
                                results_df.loc[mirrored_mask, "date"] = date_edit
                                results_df.loc[mirrored_mask, "event_type"] = event_type_edit
                                results_df.loc[mirrored_mask, "tournament_name"] = tournament_edit
                                # teammate for mirrored side stays as this player
                                results_df.loc[mirrored_mask, "points"] = points_edit
                                results_df.loc[mirrored_mask, "rank"] = rank_edit
                                results_df.loc[mirrored_mask, "prize_money"] = prize_edit

                    save_results(results_df)
                    st.success("Result updated ✅")
                    st.rerun()


# -------------------------
# PAGE: IMPORT FROM EXCEL
# -------------------------

def page_import_excel():
    st.title("📥 Import Players & Results from Excel")

    st.markdown(
        """
Upload **one Excel file** with **one sheet** containing columns:

- `first_name`
- `last_name`
- `shirt_name`
- `gender` (Male / Female)
- `fivb_id`
- `birth_date` (YYYY-MM-DD)
- `nationality`
- `season`
- `date` (YYYY-MM-DD)
- `event_type` (AVC, FIVB, AVC Multi/Zonal, Other Multi/Zonal)
- `tournament_name`
- `teammate`
- `points`
- `rank`
- `prize_money`

Each row = one result.  
Players will be created or matched using **FIVB ID**.
"""
    )

    uploaded_file = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])

    if uploaded_file is None:
        return

    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return

    st.write("Preview of uploaded data:")
    st.dataframe(df.head(), use_container_width=True)

    required_cols = [
        "first_name",
        "last_name",
        "shirt_name",
        "gender",
        "fivb_id",
        "birth_date",
        "nationality",
        "season",
        "date",
        "event_type",
        "tournament_name",
        "teammate",
        "points",
        "rank",
        "prize_money",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Missing columns: {missing}")
        return

    players_df = load_players()
    results_df = load_results()

    if st.button("✅ Import into database"):
        df["birth_date"] = df["birth_date"].astype(str)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0.0)
        df["prize_money"] = pd.to_numeric(df["prize_money"], errors="coerce").fillna(0.0)
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(0).astype(int)

        fivb_to_player_id = {}

        for _, row in df.iterrows():
            fivb = str(row["fivb_id"]).strip()
            if not fivb:
                continue

            if fivb in fivb_to_player_id:
                continue

            existing = players_df[players_df["fivb_id"] == fivb]
            if existing.empty:
                pid = new_id()
                new_player = pd.DataFrame(
                    [{
                        "player_id": pid,
                        "first_name": str(row["first_name"]).strip(),
                        "last_name": str(row["last_name"]).strip(),
                        "shirt_name": str(row["shirt_name"]).strip(),
                        "gender": str(row["gender"]).strip(),
                        "fivb_id": fivb,
                        "birth_date": str(row["birth_date"]).strip(),
                        "nationality": str(row["nationality"]).strip(),
                        "photo_file": "",
                    }]
                )
                players_df = pd.concat([players_df, new_player], ignore_index=True)
            else:
                pid = existing.iloc[0]["player_id"]

            fivb_to_player_id[fivb] = pid

        save_players(players_df)

        new_results_list = []
        for _, row in df.iterrows():
            fivb = str(row["fivb_id"]).strip()
            if fivb not in fivb_to_player_id:
                continue
            pid = fivb_to_player_id[fivb]

            new_results_list.append(
                {
                    "result_id": new_id(),
                    "player_id": pid,
                    "season": str(row["season"]),
                    "date": row["date"],
                    "event_type": str(row["event_type"]).strip(),
                    "tournament_name": str(row["tournament_name"]).strip(),
                    "teammate": str(row["teammate"]).strip(),
                    "points": float(row["points"]),
                    "rank": int(row["rank"]),
                    "prize_money": float(row["prize_money"]),
                }
            )

        if new_results_list:
            new_results_df = pd.DataFrame(new_results_list)
            results_df = pd.concat([results_df, new_results_df], ignore_index=True)
            save_results(results_df)
            st.success(f"Imported {len(new_results_list)} results and updated players ✅")
        else:
            st.info("No results to import (no valid FIVB IDs found).")


# -------------------------
# PAGE: PLAYER SEARCH
# -------------------------

def page_player_search():
    st.title("🔎 Player Search & Profile")

    players_df = load_players()
    results_df = load_results()

    if players_df.empty:
        st.info("No players yet. Please add players first.")
        return

    players_df["display"] = players_df.apply(player_display_name, axis=1)
    players_df = players_df.sort_values("display")

    selected = st.selectbox(
        "Select player",
        players_df["display"].tolist(),
    )

    row = players_df[players_df["display"] == selected].iloc[0]
    player_id = row["player_id"]

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader(f"{row['first_name']} {row['last_name']}")
        st.write(f"**Shirt name:** {row['shirt_name']}")
        st.write(f"**Gender:** {row['gender']}")
        st.write(f"**FIVB ID:** {row['fivb_id']}")
        st.write(f"**Birth date:** {row['birth_date']}")
        st.write(f"**Nationality:** {row['nationality']}")
    with col2:
        if isinstance(row["photo_file"], str) and row["photo_file"]:
            photo_rel = row["photo_file"]
            local_path = os.path.join(DATA_DIR, photo_rel)
            if USE_GITHUB:
                content, _ = github_get_file(local_path)
                if content is not None:
                    st.image(content, caption="Photo ID", use_container_width=True)
                else:
                    st.caption("Photo path saved but file not found in GitHub.")
            else:
                if os.path.exists(local_path):
                    st.image(local_path, caption="Photo ID", use_container_width=True)
                else:
                    st.caption("Photo path saved but file not found.")

    st.markdown("### Results history")
    player_results = results_df[results_df["player_id"] == player_id]
    if player_results.empty:
        st.info("No results stored for this player yet.")
    else:
        display_cols = [c for c in player_results.columns if c not in ["result_id", "player_id"]]
        player_results = player_results.sort_values("date", ascending=False)
        st.dataframe(player_results[display_cols].reset_index(drop=True), use_container_width=True)


# -------------------------
# PAGE: RANKING CALCULATOR
# -------------------------

def page_ranking_calculator():
    st.title("📊 Ranking Calculator (per player)")

    players_df = load_players()
    results_df = load_results()

    if players_df.empty:
        st.info("No players yet. Please add/import players first.")
        return

    players_df["display"] = players_df.apply(player_display_name, axis=1)
    players_df = players_df.sort_values("display")

    selected = st.selectbox(
        "Select player",
        players_df["display"].tolist(),
    )
    player_row = players_df[players_df["display"] == selected].iloc[0]
    player_id = player_row["player_id"]

    st.markdown(f"### Selected player: **{player_row['first_name']} {player_row['last_name']}**")

    mode = st.radio(
        "Point calculation period",
        ["Last 365 days from reference date", "Custom date range"],
    )

    if mode == "Last 365 days from reference date":
        ref_date = st.date_input("Reference date", value=date.today())
        result = calculate_player_points(results_df, player_id, mode="365", ref_date=ref_date)
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=365))
        with c2:
            end_date = st.date_input("End date", value=date.today())
        if start_date > end_date:
            st.error("Start date must be before end date.")
            return
        result = calculate_player_points(
            results_df,
            player_id,
            mode="custom",
            start_date=start_date,
            end_date=end_date,
        )

    st.markdown(f"**Period considered:** {result['period_text']}")

    if result["scenario"] in ["no_results", "no_results_in_period"]:
        st.warning("No results for this player in the selected period.")
        return

    st.markdown("### Points summary")
    scenario_text = "Used AVC Multi/Zonal (if any)" if result["scenario"] == "AVC_MZ_used" else "Used Other Multi/Zonal (if any)"
    st.write(f"**Scenario:** {scenario_text}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total points (selected 8)", f"{result['total_points']:.2f}")
    with col2:
        st.metric("AVC side (4 best)", f"{result['bucket1_points']:.2f}")
    with col3:
        st.metric("FIVB side (4 best)", f"{result['bucket2_points']:.2f}")

    st.markdown("### Selected results (used in sum)")
    sr = result["selected_results"].copy()
    if not sr.empty:
        sr_display_cols = [c for c in sr.columns if c not in ["result_id", "player_id"]]
        st.dataframe(sr[sr_display_cols].reset_index(drop=True), use_container_width=True)
    else:
        st.info("No selected results in this period.")

    st.markdown("### All results within the period")
    wr = result["window_results"].copy()
    if not wr.empty:
        wr_display_cols = [c for c in wr.columns if c not in ["result_id", "player_id"]]
        st.dataframe(wr[wr_display_cols].reset_index(drop=True), use_container_width=True)
    else:
        st.info("No results within this period.")


# -------------------------
# PAGE: TEAM COMBINER (Single Team)
# -------------------------

def page_team_combiner():
    st.title("👥 Team Combiner (2 players)")

    players_df = load_players()
    results_df = load_results()

    if len(players_df) < 2:
        st.info("Need at least 2 players in the database.")
        return

    players_df["display"] = players_df.apply(player_display_name, axis=1)
    players_df = players_df.sort_values("display")

    col1, col2 = st.columns(2)
    with col1:
        p1_label = st.selectbox(
            "Player A",
            players_df["display"].tolist(),
            key="team_player_a",
        )
    with col2:
        p2_label = st.selectbox(
            "Player B",
            players_df["display"].tolist(),
            key="team_player_b",
        )

    if p1_label == p2_label:
        st.error("Please choose two different players.")
        return

    p1_row = players_df[players_df["display"] == p1_label].iloc[0]
    p2_row = players_df[players_df["display"] == p2_label].iloc[0]

    st.markdown(
        f"### Selected Team:\n- **A:** {p1_row['first_name']} {p1_row['last_name']}\n"
        f"- **B:** {p2_row['first_name']} {p2_row['last_name']}"
    )

    mode = st.radio(
        "Point calculation period",
        ["Last 365 days from reference date", "Custom date range"],
        key="team_mode_single",
    )

    if mode == "Last 365 days from reference date":
        ref_date = st.date_input("Reference date", value=date.today(), key="team_ref_single")
        res1 = calculate_player_points(results_df, p1_row["player_id"], mode="365", ref_date=ref_date)
        res2 = calculate_player_points(results_df, p2_row["player_id"], mode="365", ref_date=ref_date)
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=365), key="team_start_single")
        with c2:
            end_date = st.date_input("End date", value=date.today(), key="team_end_single")
        if start_date > end_date:
            st.error("Start date must be before end date.")
            return
        res1 = calculate_player_points(results_df, p1_row["player_id"], mode="custom",
                                       start_date=start_date, end_date=end_date)
        res2 = calculate_player_points(results_df, p2_row["player_id"], mode="custom",
                                       start_date=start_date, end_date=end_date)

    st.markdown(f"**Period considered:** {res1['period_text']}")

    team_total = res1["total_points"] + res2["total_points"]

    st.markdown("### Combined points summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Player A total", f"{res1['total_points']:.2f}")
    with c2:
        st.metric("Player B total", f"{res2['total_points']:.2f}")
    with c3:
        st.metric("Team combined", f"{team_total:.2f}")

    st.markdown("#### Player A – selected results")
    sr1 = res1["selected_results"].copy()
    if not sr1.empty:
        cols1 = [c for c in sr1.columns if c not in ["result_id", "player_id"]]
        st.dataframe(sr1[cols1].reset_index(drop=True), use_container_width=True)
    else:
        st.info("No selected results for Player A in this period.")

    st.markdown("#### Player B – selected results")
    sr2 = res2["selected_results"].copy()
    if not sr2.empty:
        cols2 = [c for c in sr2.columns if c not in ["result_id", "player_id"]]
        st.dataframe(sr2[cols2].reset_index(drop=True), use_container_width=True)
    else:
        st.info("No selected results for Player B in this period.")


# -------------------------
# PAGE: MULTI-TEAM REPORT (up to 24 teams, Excel)
# -------------------------

def page_multi_team_report():
    st.title("📑 Multi-Team Report (up to 24 teams)")

    players_df = load_players()
    results_df = load_results()

    if len(players_df) < 2:
        st.info("Need at least 2 players in the database.")
        return

    players_df["display"] = players_df.apply(player_display_name, axis=1)
    players_df = players_df.sort_values("display")

    st.markdown("Select up to **24 teams** and generate a ranking report in Excel.")

    competition_name = st.text_input("Competition name", value="")
    competition_date = st.date_input("Competition date", value=date.today())

    num_teams = st.number_input("Number of teams", min_value=1, max_value=24, value=8, step=1)

    mode = st.radio(
        "Point calculation period",
        ["Last 365 days from reference date", "Custom date range"],
        key="team_mode_multi",
    )

    if mode == "Last 365 days from reference date":
        ref_date = st.date_input("Reference date", value=date.today(), key="team_ref_multi")
        start_date = None
        end_date = None
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=365), key="team_start_multi")
        with c2:
            end_date = st.date_input("End date", value=date.today(), key="team_end_multi")
        if start_date > end_date:
            st.error("Start date must be before end date.")
            return
        ref_date = None

    teams = []
    st.markdown("### Team selection")

    # For caching player results so we don't recalc many times
    player_points_cache = {}

    for i in range(int(num_teams)):
        st.markdown(f"#### Team {i+1}")
        c1, c2 = st.columns(2)
        with c1:
            p1_label = st.selectbox(
                f"Player A – Team {i+1}",
                ["(None)"] + players_df["display"].tolist(),
                key=f"multi_p1_{i}",
            )
        with c2:
            p2_label = st.selectbox(
                f"Player B – Team {i+1}",
                ["(None)"] + players_df["display"].tolist(),
                key=f"multi_p2_{i}",
            )

        if p1_label == "(None)" or p2_label == "(None)":
            continue
        if p1_label == p2_label:
            st.warning(f"Team {i+1}: Player A and B must be different. This team will be ignored.")
            continue

        p1_row = players_df[players_df["display"] == p1_label].iloc[0]
        p2_row = players_df[players_df["display"] == p2_label].iloc[0]

        teams.append((i+1, p1_row, p2_row))

    if not teams:
        st.info("No valid teams selected yet.")
        return

    if st.button("📥 Generate Multi-Team Excel Report"):
        # Calculate for each player, cache by player_id
        def get_pts(pid):
            if pid in player_points_cache:
                return player_points_cache[pid]
            if mode == "Last 365 days from reference date":
                res = calculate_player_points(results_df, pid, mode="365", ref_date=ref_date)
            else:
                res = calculate_player_points(results_df, pid, mode="custom",
                                              start_date=start_date, end_date=end_date)
            player_points_cache[pid] = res
            return res

        team_rows = []
        unique_players = {}  # player_id -> (row, points_result)

        for team_no, p1_row, p2_row in teams:
            p1_id = p1_row["player_id"]
            p2_id = p2_row["player_id"]

            res1 = get_pts(p1_id)
            res2 = get_pts(p2_id)

            # Keep in map for breakdown
            unique_players[p1_id] = (p1_row, res1)
            unique_players[p2_id] = (p2_row, res2)

            team_total = res1["total_points"] + res2["total_points"]

            nat = p1_row["nationality"]  # both same as per your rule
            team_name = f"{shirt_or_name(p1_row)} / {shirt_or_name(p2_row)}"

            team_rows.append({
                "Team No": team_no,
                "Nationality": nat,
                "Team Name": team_name,
                "Player A AVC Points": res1["bucket1_points"],
                "Player A FIVB Points": res1["bucket2_points"],
                "Player B AVC Points": res2["bucket1_points"],
                "Player B FIVB Points": res2["bucket2_points"],
                "Team Total Points": team_total,
            })

        df_teams = pd.DataFrame(team_rows)
        if df_teams.empty:
            st.warning("No teams to include in report.")
            return

        df_teams = df_teams.sort_values("Team Total Points", ascending=False).reset_index(drop=True)
        df_teams.insert(0, "Position", range(1, len(df_teams) + 1))

        # Create Excel in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # TAB 1: Entry List
            sheet_name1 = "Entry List"
            df_teams.to_excel(writer, sheet_name=sheet_name1, index=False, startrow=4)

            wb = writer.book
            ws1 = wb[sheet_name1]

            # Header rows for logos & text
            ws1["A1"] = ""  # left logo placeholder
            ws1["I1"] = ""  # right logo placeholder

            ws1["C1"] = competition_name
            ws1["C2"] = competition_date.isoformat()
            ws1["C3"] = f"Confirmed Entry List ({len(df_teams)} Teams)"

            # TAB 2: Breakdown
            sheet_name2 = "Breakdown"
            ws2 = wb.create_sheet(title=sheet_name2)

            row_idx = 1
            for pid, (prow, pres) in unique_players.items():
                name = f"{prow['first_name']} {prow['last_name']}"
                nat = prow["nationality"]
                gender = prow["gender"]

                # Spacer row
                if row_idx > 1:
                    row_idx += 1

                ws2.cell(row=row_idx, column=1, value=f"{name} ({nat}, {gender})")
                row_idx += 1

                selected = pres["selected_results"].copy()
                if selected.empty:
                    ws2.cell(row=row_idx, column=1, value="No selected results in this period.")
                    row_idx += 1
                    continue

                # AVC side = AVC + AVC MZ
                avc_side = selected[selected["event_type"].isin(["AVC", "AVC Multi/Zonal"])]
                fivb_side = selected[selected["event_type"].isin(["FIVB", "Other Multi/Zonal"])]

                # AVC section
                ws2.cell(row=row_idx, column=1, value="AVC Side (Best 4)")
                row_idx += 1
                header = ["Season", "Date", "Event Type", "Tournament", "Teammate", "Points", "Rank", "Prize Money"]
                for col_idx, h in enumerate(header, start=1):
                    ws2.cell(row=row_idx, column=col_idx, value=h)
                row_idx += 1

                if avc_side.empty:
                    ws2.cell(row=row_idx, column=1, value="(No AVC-side events selected)")
                    row_idx += 1
                else:
                    avc_side = avc_side.sort_values("points", ascending=False)
                    for _, r in avc_side.iterrows():
                        ws2.cell(row=row_idx, column=1, value=r["season"])
                        ws2.cell(row=row_idx, column=2, value=str(r["date"]))
                        ws2.cell(row=row_idx, column=3, value=r["event_type"])
                        ws2.cell(row=row_idx, column=4, value=r["tournament_name"])
                        ws2.cell(row=row_idx, column=5, value=r["teammate"])
                        ws2.cell(row=row_idx, column=6, value=float(r["points"]))
                        ws2.cell(row=row_idx, column=7, value=float(r["rank"]))
                        ws2.cell(row=row_idx, column=8, value=float(r["prize_money"]))
                        row_idx += 1

                # FIVB section
                row_idx += 1
                ws2.cell(row=row_idx, column=1, value="FIVB Side (Best 4)")
                row_idx += 1
                for col_idx, h in enumerate(header, start=1):
                    ws2.cell(row=row_idx, column=col_idx, value=h)
                row_idx += 1

                if fivb_side.empty:
                    ws2.cell(row=row_idx, column=1, value="(No FIVB-side events selected)")
                    row_idx += 1
                else:
                    fivb_side = fivb_side.sort_values("points", ascending=False)
                    for _, r in fivb_side.iterrows():
                        ws2.cell(row=row_idx, column=1, value=r["season"])
                        ws2.cell(row=row_idx, column=2, value=str(r["date"]))
                        ws2.cell(row=row_idx, column=3, value=r["event_type"])
                        ws2.cell(row=row_idx, column=4, value=r["tournament_name"])
                        ws2.cell(row=row_idx, column=5, value=r["teammate"])
                        ws2.cell(row=row_idx, column=6, value=float(r["points"]))
                        ws2.cell(row=row_idx, column=7, value=float(r["rank"]))
                        ws2.cell(row=row_idx, column=8, value=float(r["prize_money"]))
                        row_idx += 1

        output.seek(0)
        st.download_button(
            label="⬇️ Download Excel Report",
            data=output,
            file_name="confirmed_entry_list.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# -------------------------
# PAGE: AVC RANKINGS (MEN & WOMEN) – FANCY CARDS
# -------------------------

def page_avc_rankings():
    st.title("🏆 AVC Rankings")

    # ----- CSS styling for row layout -----
    st.markdown("""
    <style>
    .rank-card {
        border: 1px solid #e2e2e2;
        border-radius: 10px;
        margin: 10px 0;
        overflow: hidden;
    }
    .rank-summary {
        display: flex;
        padding: 12px;
        align-items: center;
        cursor: pointer;
        background-color: #fafafa;
    }
    .rank-summary:hover {
        background-color: #eef3ff;
    }
    .rank-num {
        width: 40px;
        font-weight: 700;
        font-size: 18px;
        color: #003b9b;
    }
    .rank-nat {
        width: 60px;
        font-weight: 600;
        font-size: 16px;
        color: #444;
    }
    .rank-team {
        flex-grow: 1;
        font-weight: 700;
        font-size: 17px;
        color: #111;
    }
    .rank-pts {
        font-weight: 700;
        font-size: 17px;
        color: #111;
    }
    .rank-details {
        background: white;
        padding: 16px 20px;
        border-top: 1px solid #ddd;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    Ranking of teams based on their **4 best AVC results** plus **4 best FIVB results** 
    within the last 365 days.  
    Rankings are updated every Monday after AVC-recognized events that grant AVC Ranking Points.
    """)

    players_df = load_players()
    results_df = load_results()

    if players_df.empty or results_df.empty:
        st.info("No players or results available yet.")
        return

    # Mapping: full name → list of IDs
    name_to_id = {}
    for _, r in players_df.iterrows():
        full = f"{r['first_name']} {r['last_name']}".strip()
        name_to_id.setdefault(full, []).append(r["player_id"])

    # Detect valid pairs from results
    pair_keys = set()
    for _, res in results_df.iterrows():
        pid = res["player_id"]
        teammate = str(res.get("teammate", "")).strip()
        if teammate and teammate in name_to_id:
            tm_id = name_to_id[teammate][0]
            if tm_id != pid:
                pair_keys.add(tuple(sorted([pid, tm_id])))

    if not pair_keys:
        st.info("No eligible teams found.")
        return

    ref_date = date.today()
    pts_cache = {}

    def get_pts(pid):
        if pid not in pts_cache:
            pts_cache[pid] = calculate_player_points(results_df, pid, mode="365", ref_date=ref_date)
        return pts_cache[pid]

    men_rows, women_rows = [], []
    men_det, women_det = {}, {}

    # Build rows for men & women rankings
    for pid_a, pid_b in pair_keys:
        pa = get_player_by_id(players_df, pid_a)
        pb = get_player_by_id(players_df, pid_b)
        if pa is None or pb is None:
            continue

        # Only same-gender pairs
        if pa["gender"] == "Male" and pb["gender"] == "Male":
            cat = "Men"
        elif pa["gender"] == "Female" and pb["gender"] == "Female":
            cat = "Women"
        else:
            continue

        r1 = get_pts(pid_a)
        r2 = get_pts(pid_b)
        total = r1["total_points"] + r2["total_points"]

        nat = pa["nationality"]
        team_name = f"{shirt_or_name(pa)} / {shirt_or_name(pb)}"
        key = f"{pid_a}|{pid_b}"

        row = {
            "key": key,
            "Nationality": nat,
            "Team Name": team_name,
            "Total": total,
        }
        data = {"p1": pa, "p2": pb, "r1": r1, "r2": r2}

        if cat == "Men":
            men_rows.append(row)
            men_det[key] = data
        else:
            women_rows.append(row)
            women_det[key] = data

    # Men / Women toggle
    tab = st.radio("Select category", ["Men", "Women"])

    if tab == "Men":
        rows = men_rows
        details = men_det
    else:
        rows = women_rows
        details = women_det

    if not rows:
        st.info("No teams in this category.")
        return

    # Sort by total points and add rank
    df = pd.DataFrame(rows)
    df = df.sort_values("Total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))

    # Search bar
    search = st.text_input("🔍 Search team or player name").lower().strip()

    filtered_rows = []
    for _, row in df.iterrows():
        key = row["key"]
        d = details[key]
        p1, p2 = d["p1"], d["p2"]

        content = (
            row["Team Name"].lower()
            + p1["first_name"].lower()
            + p1["last_name"].lower()
            + p2["first_name"].lower()
            + p2["last_name"].lower()
            + str(p1.get("shirt_name", "")).lower()
            + str(p2.get("shirt_name", "")).lower()
        )

        if search and search not in content:
            continue

        filtered_rows.append(row)

    if not filtered_rows:
        st.info("No matching teams.")
        return

    # Render each team as a <details> card
    for row in filtered_rows:
        key = row["key"]
        d = details[key]
        p1, p2 = d["p1"], d["p2"]
        r1, r2 = d["r1"], d["r2"]

        rank = row["Rank"]
        nat = row["Nationality"]
        team_name = row["Team Name"]
        total = row["Total"]

        # Start HTML card
        html = f"""<details class="rank-card">
<summary class="rank-summary">
<div class="rank-num">{rank}</div>
<div class="rank-nat">{nat}</div>
<div class="rank-team">{team_name}</div>
<div class="rank-pts">{total:.2f} pts</div>
</summary>
<div class="rank-details">

<h4 style="margin-top:0;">Player Breakdown</h4>

<table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
<tr style="background:#f3f6ff; font-weight:600;">
    <td style="padding:6px; border:1px solid #ccc;">Player</td>
    <td style="padding:6px; border:1px solid #ccc;">Shirt Name</td>
    <td style="padding:6px; border:1px solid #ccc;">AVC (Best 4)</td>
    <td style="padding:6px; border:1px solid #ccc;">FIVB (Best 4)</td>
    <td style="padding:6px; border:1px solid #ccc;">Total</td>
</tr>

<tr>
    <td style="padding:6px; border:1px solid #ccc;">{p1['first_name']} {p1['last_name']}</td>
    <td style="padding:6px; border:1px solid #ccc;">{shirt_or_name(p1)}</td>
    <td style="padding:6px; border:1px solid #ccc;">{r1['bucket1_points']:.2f}</td>
    <td style="padding:6px; border:1px solid #ccc;">{r1['bucket2_points']:.2f}</td>
    <td style="padding:6px; border:1px solid #ccc; font-weight:700;">{r1['total_points']:.2f}</td>
</tr>

<tr>
    <td style="padding:6px; border:1px solid #ccc;">{p2['first_name']} {p2['last_name']}</td>
    <td style="padding:6px; border:1px solid #ccc;">{shirt_or_name(p2)}</td>
    <td style="padding:6px; border:1px solid #ccc;">{r2['bucket1_points']:.2f}</td>
    <td style="padding:6px; border:1px solid #ccc;">{r2['bucket2_points']:.2f}</td>
    <td style="padding:6px; border:1px solid #ccc; font-weight:700;">{r2['total_points']:.2f}</td>
</tr>
</table>

<h4>Selected Events Used in Calculation</h4>

<b>Player A – {p1['first_name']} {p1['last_name']}</b><br>
<table style="width:100%; border-collapse:collapse; margin:8px 0 18px 0;">
<tr style="background:#eef2ff; font-weight:600;">
    <td style="padding:5px; border:1px solid #ccc;">Date</td>
    <td style="padding:5px; border:1px solid #ccc;">Event</td>
    <td style="padding:5px; border:1px solid #ccc;">Tournament</td>
    <td style="padding:5px; border:1px solid #ccc;">Points</td>
</tr>
"""

        # Player A events
        sel1 = r1["selected_results"]
        for _, ev in sel1.iterrows():
            html += f"""
<tr>
    <td style="padding:5px; border:1px solid #ddd;">{ev['date']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['event_type']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['tournament_name']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['points']}</td>
</tr>
"""

        html += "</table>"

        # Player B events
        html += f"""
<b>Player B – {p2['first_name']} {p2['last_name']}</b><br>
<table style="width:100%; border-collapse:collapse; margin:8px 0 8px 0;">
<tr style="background:#eef2ff; font-weight:600;">
    <td style="padding:5px; border:1px solid #ccc;">Date</td>
    <td style="padding:5px; border:1px solid #ccc;">Event</td>
    <td style="padding:5px; border:1px solid #ccc;">Tournament</td>
    <td style="padding:5px; border:1px solid #ccc;">Points</td>
</tr>
"""

        sel2 = r2["selected_results"]
        for _, ev in sel2.iterrows():
            html += f"""
<tr>
    <td style="padding:5px; border:1px solid #ddd;">{ev['date']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['event_type']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['tournament_name']}</td>
    <td style="padding:5px; border:1px solid #ddd;">{ev['points']}</td>
</tr>
"""

        html += "</table></div></details>"

        st.markdown(html, unsafe_allow_html=True)


# -------------------------
# MAIN SIDEBAR / ROUTER
# -------------------------

def main():
    st.sidebar.title("🏐 Player Database")
    if USE_GITHUB:
        st.sidebar.success("GitHub storage: ON")
    else:
        st.sidebar.warning("GitHub storage: OFF (local / ephemeral on Streamlit Cloud)")

    page = st.sidebar.radio(
        "Go to",
        [
            "Add / Edit Player",
            "Import from Excel",
            "Player Search",
            "Ranking Calculator",
            "Team Combiner (Single)",
            "Multi-Team Report",
            "AVC Rankings",
        ],
    )

    if page == "Add / Edit Player":
        page_add_edit_player()
    elif page == "Import from Excel":
        page_import_excel()
    elif page == "Player Search":
        page_player_search()
    elif page == "Ranking Calculator":
        page_ranking_calculator()
    elif page == "Team Combiner (Single)":
        page_team_combiner()
    elif page == "Multi-Team Report":
        page_multi_team_report()
    elif page == "AVC Rankings":
        page_avc_rankings()


if __name__ == "__main__":
    main()
