import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import uuid

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


# -------------------------
# UTIL FUNCTIONS
# -------------------------

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)


def load_players():
    ensure_dirs()
    if os.path.exists(PLAYERS_FILE):
        df = pd.read_csv(PLAYERS_FILE, dtype=str)
    else:
        df = pd.DataFrame(columns=PLAYER_COLUMNS)
    if "birth_date" in df.columns:
        df["birth_date"] = df["birth_date"].fillna("")
    return df


def load_results():
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
    ensure_dirs()
    df.to_csv(PLAYERS_FILE, index=False)


def save_results(df):
    ensure_dirs()
    df.to_csv(RESULTS_FILE, index=False)


def new_id():
    return str(uuid.uuid4())


def player_display_name(row):
    base = f"{row['first_name']} {row['last_name']}".strip()
    if isinstance(row.get("fivb_id"), str) and row["fivb_id"].strip():
        return f"{base} (FIVB: {row['fivb_id']})"
    return base


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
        col1, col2, col3 = st.columns(3)

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
            fivb_id = st.text_input(
                "FIVB ID",
                value=player_row["fivb_id"] if player_row is not None else "",
            )
            nationality = st.text_input(
                "Nationality (e.g. THA, CHN, JPN)",
                value=player_row["nationality"] if player_row is not None else "",
            )
        with col3:
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

        ensure_dirs()

        if player_row is None:
            # New player
            player_id = new_id()
            photo_path = ""
            if photo_file is not None:
                ext = os.path.splitext(photo_file.name)[1]
                photo_filename = f"{player_id}{ext}"
                photo_path = os.path.join("photos", photo_filename)
                with open(os.path.join(DATA_DIR, photo_path), "wb") as f:
                    f.write(photo_file.getbuffer())

            new_player = pd.DataFrame(
                [{
                    "player_id": player_id,
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
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
                photo_path = os.path.join("photos", photo_filename)
                with open(os.path.join(DATA_DIR, photo_path), "wb") as f:
                    f.write(photo_file.getbuffer())

            players_df.loc[idx, "first_name"] = first_name.strip()
            players_df.loc[idx, "last_name"] = last_name.strip()
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
                teammate_row = players_df[
                    (players_df["first_name"] + " " + players_df["last_name"]) == teammate
                ]
                if not teammate_row.empty:
                    teammate_id = teammate_row.iloc[0]["player_id"]
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
            st.experimental_rerun()

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
                    mask = results_df["result_id"] == res_id
                    results_df.loc[mask, "season"] = season_edit
                    results_df.loc[mask, "date"] = date_edit
                    results_df.loc[mask, "event_type"] = event_type_edit
                    results_df.loc[mask, "tournament_name"] = tournament_edit
                    results_df.loc[mask, "teammate"] = teammate_edit
                    results_df.loc[mask, "points"] = points_edit
                    results_df.loc[mask, "rank"] = rank_edit
                    results_df.loc[mask, "prize_money"] = prize_edit

                    save_results(results_df)
                    st.success("Result updated ✅")
                    st.experimental_rerun()
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
        st.write(f"**FIVB ID:** {row['fivb_id']}")
        st.write(f"**Birth date:** {row['birth_date']}")
        st.write(f"**Nationality:** {row['nationality']}")
    with col2:
        if isinstance(row["photo_file"], str) and row["photo_file"]:
            photo_path = os.path.join(DATA_DIR, row["photo_file"])
            if os.path.exists(photo_path):
                st.image(photo_path, caption="Photo ID", use_container_width=True)
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
# PAGE: TEAM COMBINER
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
        key="team_mode",
    )

    if mode == "Last 365 days from reference date":
        ref_date = st.date_input("Reference date", value=date.today(), key="team_ref_date")
        res1 = calculate_player_points(results_df, p1_row["player_id"], mode="365", ref_date=ref_date)
        res2 = calculate_player_points(results_df, p2_row["player_id"], mode="365", ref_date=ref_date)
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=365), key="team_start_date")
        with c2:
            end_date = st.date_input("End date", value=date.today(), key="team_end_date")
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

    st.markdown("---")
    st.markdown("### Tournaments where they appear as teammates (from perspective of each)")

    p1_results = results_df[results_df["player_id"] == p1_row["player_id"]]
    p2_results = results_df[results_df["player_id"] == p2_row["player_id"]]

    nameA = f"{p1_row['first_name']} {p1_row['last_name']}".strip()
    nameB = f"{p2_row['first_name']} {p2_row['last_name']}".strip()

    together_a = p1_results[p1_results["teammate"].str.contains(nameB, na=False)]
    together_b = p2_results[p2_results["teammate"].str.contains(nameA, na=False)]

    if together_a.empty and together_b.empty:
        st.info("No tournaments found where they are listed as teammates (based on 'teammate' name text).")
    else:
        colA, colB = st.columns(2)
        with colA:
            st.markdown(f"**View from {nameA}'s results**")
            if not together_a.empty:
                colsA = [c for c in together_a.columns if c not in ['result_id', 'player_id']]
                st.dataframe(together_a.sort_values('date', ascending=False)[colsA], use_container_width=True)
            else:
                st.info("No teammate entries from Player A's side.")
        with colB:
            st.markdown(f"**View from {nameB}'s results**")
            if not together_b.empty:
                colsB = [c for c in together_b.columns if c not in ['result_id', 'player_id']]
                st.dataframe(together_b.sort_values('date', ascending=False)[colsB], use_container_width=True)
            else:
                st.info("No teammate entries from Player B's side.")
# -------------------------
# MAIN SIDEBAR / ROUTER
# -------------------------

def main():
    st.sidebar.title("🏐 Player Database")
    page = st.sidebar.radio(
        "Go to",
        [
            "Add / Edit Player",
            "Import from Excel",
            "Player Search",
            "Ranking Calculator",
            "Team Combiner",
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
    elif page == "Team Combiner":
        page_team_combiner()


if __name__ == "__main__":
    main()
