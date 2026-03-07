"""
F1 "What If" Race Simulator — Streamlit UI
==========================================
Wraps the race_simulator notebook logic into an interactive web app.
Valid seasons: 2023, 2024, 2025 (model training range).
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import joblib
import json
import copy
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from collections import Counter
import warnings
warnings.filterwarnings("ignore")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Race Simulator",
    page_icon="🏎️",
    layout="wide",
)

# ── Driver / team colours ─────────────────────────────────────────────────────
DRIVER_COLOURS = {
    "VER": "#3671C6", "PER": "#3671C6",
    "LEC": "#E8002D", "SAI": "#E8002D",
    "HAM": "#27F4D2", "RUS": "#27F4D2",
    "NOR": "#FF8000", "PIA": "#FF8000",
    "ALO": "#358C75", "STR": "#358C75",
    "GAS": "#0093CC", "OCO": "#0093CC",
    "ALB": "#64C4FF", "SAR": "#64C4FF",
    "HUL": "#B6BABD", "MAG": "#B6BABD",
    "TSU": "#6692FF", "RIC": "#6692FF",
    "BOT": "#C92D4B", "ZHO": "#C92D4B",
}

COMPOUND_MAP   = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}
COMPOUND_NAMES = {0: "SOFT", 1: "MEDIUM", 2: "HARD"}
BASE_LAPTIME   = 95.0
PIT_LOSS_MEAN  = 23.5
PIT_LOSS_STD   = 0.8
SAFETY_CAR_DELTA = 30.0
DRS_WINDOW     = 1.0

# ── Circuit configs ───────────────────────────────────────────────────────────
CIRCUITS = {
    "Bahrain":    {"total_laps": 57, "track_temp": 35.0, "air_temp": 28.0},
    "Saudi Arabia": {"total_laps": 50, "track_temp": 32.0, "air_temp": 27.0},
    "Australia":  {"total_laps": 58, "track_temp": 28.0, "air_temp": 22.0},
    "Miami":      {"total_laps": 57, "track_temp": 38.0, "air_temp": 30.0},
    "Monaco":     {"total_laps": 78, "track_temp": 40.0, "air_temp": 25.0},
    "Silverstone":{"total_laps": 52, "track_temp": 30.0, "air_temp": 20.0},
    "Monza":      {"total_laps": 53, "track_temp": 33.0, "air_temp": 26.0},
    "Suzuka":     {"total_laps": 53, "track_temp": 29.0, "air_temp": 22.0},
}

# ── Default grids per circuit ─────────────────────────────────────────────────
DEFAULT_GRID = [
    {"driver": "VER", "team": "Red Bull Racing", "compound": 0, "tyre_age": 1},
    {"driver": "LEC", "team": "Ferrari",          "compound": 0, "tyre_age": 1},
    {"driver": "SAI", "team": "Ferrari",          "compound": 0, "tyre_age": 1},
    {"driver": "PER", "team": "Red Bull Racing",  "compound": 0, "tyre_age": 1},
    {"driver": "NOR", "team": "McLaren",          "compound": 0, "tyre_age": 1},
    {"driver": "ALO", "team": "Aston Martin",     "compound": 0, "tyre_age": 1},
]

DEFAULT_STRATEGIES = {
    "VER": [(15, 1), (40, 2)],
    "LEC": [(16, 1), (41, 2)],
    "SAI": [(17, 1), (39, 2)],
    "PER": [(14, 1), (38, 2)],
    "NOR": [(18, 1), (40, 2)],
    "ALO": [(19, 1), (42, 2)],
}

# ── Model loading (cached) ────────────────────────────────────────────────────
@st.cache_resource
def load_models(model_dir: str):
    lap_model    = joblib.load(f"analysis/models/lap_time_model.pkl")
    ovt_model    = joblib.load(f"analysis/models/overtaking_model.pkl")
    team_encoder = joblib.load(f"analysis/models/team_encoder.pkl")
    with open(f"analysis/models/compound_map.json") as f:
        compound_map = json.load(f)
    return lap_model, ovt_model, team_encoder, compound_map

def encode_team(team_encoder, team_name: str) -> int:
    try:
        return int(team_encoder.transform([team_name])[0])
    except Exception:
        return 0

# ── Pace factors (cached per season) ─────────────────────────────────────────
@st.cache_data
def calculate_pace_factors(season: int, n_races: int = 5) -> dict:
    import fastf1
    team_times, team_counts = {}, {}
    progress = st.progress(0, text=f"Loading {season} pace factors...")
    for i, round_num in enumerate(range(1, n_races + 1)):
        try:
            session = fastf1.get_session(season, round_num, "R")
            session.load(telemetry=False)
            laps = session.laps.pick_quicklaps()
            laps = laps[laps["LapTime"].notna()]
            race_avg = laps.groupby("Team")["LapTime"].mean().dt.total_seconds()
            for team, avg in race_avg.items():
                team_times[team]  = team_times.get(team, 0) + avg
                team_counts[team] = team_counts.get(team, 0) + 1
        except Exception:
            pass
        progress.progress((i + 1) / n_races,
                          text=f"Loaded round {round_num}/{n_races}...")
    progress.empty()
    season_avg = {t: team_times[t] / team_counts[t]
                  for t in team_times if team_counts[t] >= 2}
    fastest = min(season_avg.values())
    return {t: v / fastest for t, v in season_avg.items()}

# ── Dataclass ─────────────────────────────────────────────────────────────────
@dataclass
class DriverState:
    driver:       str
    team_encoded: int
    team_name:    str
    position:     int
    compound:     int
    tyre_age:     int
    race_time:    float = 0.0
    laps_done:    int   = 0
    retired:      bool  = False
    strategy:     List[Tuple[int, int]] = field(default_factory=list)

    def next_pit(self) -> Optional[Tuple[int, int]]:
        upcoming = [(l, c) for l, c in self.strategy if l > self.laps_done]
        return upcoming[0] if upcoming else None

# ── Simulation functions ──────────────────────────────────────────────────────
def predict_lap_time_batch(drivers, lap, config, lap_model):
    active = [d for d in drivers if not d.retired]
    if not active:
        return {}
    rows = [{
        "CompoundEncoded": d.compound, "TyreLife": d.tyre_age,
        "TeamEncoded": d.team_encoded, "LapNumber": lap,
        "TrackTemp": config["track_temp"], "AirTemp": config["air_temp"],
        "RainfallEncoded": config["rainfall"],
    } for d in active]
    features  = pd.DataFrame(rows)
    deltas    = lap_model.predict(features)
    factors   = np.array([config["pace_factors"].get(d.team_name, 1.0) for d in active])
    noise     = np.random.normal(0, 0.15, size=len(active))
    lap_times = (BASE_LAPTIME + deltas) * factors + noise
    return {d.driver: t for d, t in zip(active, lap_times)}

def apply_pit_stop(driver, lap):
    next_stop = driver.next_pit()
    if next_stop is None:
        return False, 0.0
    pit_lap, new_compound = next_stop
    if pit_lap != lap:
        return False, 0.0
    driver.compound = new_compound
    driver.tyre_age = 1
    return True, np.random.normal(PIT_LOSS_MEAN, PIT_LOSS_STD)

def check_overtakes(drivers, ovt_model):
    pace_order = sorted(drivers, key=lambda d: d.race_time)
    for i in range(1, len(pace_order)):
        car_behind = pace_order[i]
        car_ahead  = pace_order[i - 1]
        if car_behind.retired or car_ahead.retired:
            continue
        gap = car_behind.race_time - car_ahead.race_time
        if gap > DRS_WINDOW:
            continue
        tyre_delta = car_ahead.tyre_age - car_behind.tyre_age
        features = pd.DataFrame([{
            "GapAhead": gap, "TyreDelta": tyre_delta,
            "CompoundEncoded": car_behind.compound,
            "CompoundAheadEncoded": car_ahead.compound,
            "TyreLife": car_behind.tyre_age,
            "TyreLifeAhead": car_ahead.tyre_age,
            "LapNumber": car_behind.laps_done,
            "Position": car_behind.position,
        }])
        prob = ovt_model.predict_proba(features)[0][1]
        if np.random.random() < prob:
            if car_ahead.position == car_behind.position - 1:
                car_behind.position, car_ahead.position = (
                    car_ahead.position, car_behind.position)
                pace_order[i], pace_order[i - 1] = pace_order[i - 1], pace_order[i]
    return sorted(pace_order, key=lambda d: d.position)

def simulate_race(config, grid, lap_model, ovt_model):
    drivers = copy.deepcopy(grid)
    sc_active, sc_laps_remaining = False, 0
    for lap in range(1, config["total_laps"] + 1):
        if sc_active:
            sc_laps_remaining -= 1
            if sc_laps_remaining <= 0:
                sc_active = False
        elif np.random.random() < config["sc_prob_per_lap"]:
            sc_active, sc_laps_remaining = True, 4
        lap_times = predict_lap_time_batch(drivers, lap, config, lap_model)
        for driver in drivers:
            if driver.retired:
                continue
            lap_time = lap_times[driver.driver]
            if sc_active:
                lap_time += SAFETY_CAR_DELTA
            did_pit, pit_cost = apply_pit_stop(driver, lap)
            if did_pit:
                lap_time += pit_cost
            driver.race_time += lap_time
            driver.tyre_age  += 1
            driver.laps_done  = lap
        if not sc_active:
            drivers = check_overtakes(drivers, ovt_model)
    drivers = sorted(drivers, key=lambda d: d.race_time)
    for i, d in enumerate(drivers):
        d.position = i + 1
    return drivers

def run_monte_carlo(config, grid, lap_model, ovt_model, n_runs):
    win_counts = Counter()
    bar = st.progress(0, text="Running simulations...")
    for i in range(n_runs):
        result = simulate_race(config, grid, lap_model, ovt_model)
        win_counts[result[0].driver] += 1
        if (i + 1) % max(1, n_runs // 20) == 0:
            bar.progress((i + 1) / n_runs,
                         text=f"Simulation {i+1}/{n_runs}...")
    bar.empty()
    return {d: c / n_runs for d, c in win_counts.most_common()}

# ── Position trace with overtake probability heatmap ─────────────────────────
def run_trace_race(config, grid, lap_model, ovt_model):
    """Run one race, recording positions and overtake probabilities per lap."""
    drivers = copy.deepcopy(grid)
    sc_active, sc_laps_remaining = False, 0
    position_history = {d.driver: [] for d in drivers}
    # overtake_probs[lap] = {driver_behind: prob}
    overtake_probs = {d.driver: [] for d in drivers}

    for lap in range(1, config["total_laps"] + 1):
        if sc_active:
            sc_laps_remaining -= 1
            if sc_laps_remaining <= 0:
                sc_active = False
        elif np.random.random() < config["sc_prob_per_lap"]:
            sc_active, sc_laps_remaining = True, 4

        lap_times = predict_lap_time_batch(drivers, lap, config, lap_model)
        for driver in drivers:
            if driver.retired:
                continue
            lap_time = lap_times[driver.driver]
            if sc_active:
                lap_time += SAFETY_CAR_DELTA
            did_pit, pit_cost = apply_pit_stop(driver, lap)
            if did_pit:
                lap_time += pit_cost
            driver.race_time += lap_time
            driver.tyre_age  += 1
            driver.laps_done  = lap

        # Record overtake probs BEFORE resolving overtakes
        pace_order = sorted(drivers, key=lambda d: d.race_time)
        lap_ovt_probs = {}
        for i in range(1, len(pace_order)):
            car_behind = pace_order[i]
            car_ahead  = pace_order[i - 1]
            if car_behind.retired or car_ahead.retired:
                lap_ovt_probs[car_behind.driver] = 0.0
                continue
            gap = car_behind.race_time - car_ahead.race_time
            if gap > DRS_WINDOW:
                lap_ovt_probs[car_behind.driver] = 0.0
                continue
            tyre_delta = car_ahead.tyre_age - car_behind.tyre_age
            features = pd.DataFrame([{
                "GapAhead": gap, "TyreDelta": tyre_delta,
                "CompoundEncoded": car_behind.compound,
                "CompoundAheadEncoded": car_ahead.compound,
                "TyreLife": car_behind.tyre_age,
                "TyreLifeAhead": car_ahead.tyre_age,
                "LapNumber": car_behind.laps_done,
                "Position": car_behind.position,
            }])
            prob = ovt_model.predict_proba(features)[0][1]
            lap_ovt_probs[car_behind.driver] = prob

        for d in drivers:
            overtake_probs[d.driver].append(lap_ovt_probs.get(d.driver, 0.0))

        if not sc_active:
            drivers = check_overtakes(drivers, ovt_model)

        sorted_d = sorted(drivers, key=lambda d: d.race_time)
        for i, d in enumerate(sorted_d):
            position_history[d.driver].append(i + 1)

    return position_history, overtake_probs

# ── Plotting ──────────────────────────────────────────────────────────────────
def plot_results(probs, position_history, overtake_probs, season, circuit, total_laps):
    driver_list = list(probs.keys())
    fig = plt.figure(figsize=(18, 10))
    fig.patch.set_facecolor("#0f0f0f")
    gs = fig.add_gridspec(2, 2, hspace=0.4, wspace=0.35)
    ax1 = fig.add_subplot(gs[:, 0])   # win probability — full height left
    ax2 = fig.add_subplot(gs[0, 1])   # position trace — top right
    ax3 = fig.add_subplot(gs[1, 1])   # overtake heatmap — bottom right

    title_colour = "#f0f0f0"
    fig.suptitle(f"🏎️  {circuit} GP  ·  {season} Pace Factors",
                 fontsize=15, fontweight="bold", color=title_colour, y=1.01)

    # ── Chart 1: Win probability ──────────────────────────────────────────────
    ax1.set_facecolor("#1a1a1a")
    win_pcts = [probs[d] * 100 for d in driver_list]
    colours  = [DRIVER_COLOURS.get(d, "#888888") for d in driver_list]
    bars = ax1.barh(driver_list[::-1], win_pcts[::-1],
                    color=colours[::-1], edgecolor="#0f0f0f", height=0.65)
    for bar, pct in zip(bars, win_pcts[::-1]):
        ax1.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                 f"{pct:.1f}%", va="center", fontsize=11,
                 fontweight="bold", color=title_colour)
    ax1.set_xlabel("Win Probability (%)", fontsize=11, color=title_colour)
    ax1.set_title(f"Win Probability — {sum(int(v*len(probs)) for v in probs.values())+1:,} Simulations",
                  fontsize=12, color=title_colour, pad=10)
    ax1.set_xlim(0, max(win_pcts) * 1.25)
    ax1.tick_params(colors=title_colour)
    for spine in ax1.spines.values():
        spine.set_visible(False)
    ax1.grid(axis="x", alpha=0.15, color="white")

    # ── Chart 2: Position trace ───────────────────────────────────────────────
    ax2.set_facecolor("#1a1a1a")
    laps = list(range(1, total_laps + 1))
    for driver, positions in position_history.items():
        colour = DRIVER_COLOURS.get(driver, "#888888")
        ax2.plot(laps, positions, color=colour, linewidth=2.2, alpha=0.9)
        ax2.text(laps[-1] + 0.5, positions[-1], driver,
                 va="center", fontsize=8, color=colour, fontweight="bold")
    ax2.set_xlabel("Lap", fontsize=10, color=title_colour)
    ax2.set_ylabel("Position", fontsize=10, color=title_colour)
    ax2.set_title("Position Trace — Single Race Example", fontsize=11,
                  color=title_colour, pad=8)
    ax2.set_ylim(len(position_history) + 0.5, 0.5)
    ax2.set_yticks(range(1, len(position_history) + 1))
    ax2.set_xlim(1, total_laps + 5)
    ax2.tick_params(colors=title_colour)
    for spine in ax2.spines.values():
        spine.set_visible(False)
    ax2.grid(alpha=0.1, color="white")

    # ── Chart 3: Overtake probability heatmap ────────────────────────────────
    ax3.set_facecolor("#1a1a1a")
    drivers_ordered = list(overtake_probs.keys())
    # Downsample to every 3rd lap for readability
    sample_laps = list(range(0, total_laps, 3))
    heat_data = np.array([
        [overtake_probs[d][l] for l in sample_laps]
        for d in drivers_ordered
    ])
    im = ax3.imshow(heat_data, aspect="auto", cmap="YlOrRd",
                    vmin=0, vmax=0.4, interpolation="nearest")
    ax3.set_yticks(range(len(drivers_ordered)))
    ax3.set_yticklabels(drivers_ordered, fontsize=9, color=title_colour)
    ax3.set_xticks(range(0, len(sample_laps), 5))
    ax3.set_xticklabels(
        [str(sample_laps[i] + 1) for i in range(0, len(sample_laps), 5)],
        fontsize=8, color=title_colour)
    ax3.set_xlabel("Lap", fontsize=10, color=title_colour)
    ax3.set_title("Overtake Probability per Lap", fontsize=11,
                  color=title_colour, pad=8)
    cb = plt.colorbar(im, ax=ax3, fraction=0.046, pad=0.04)
    cb.ax.yaxis.set_tick_params(color=title_colour)
    cb.outline.set_visible(False)
    plt.setp(cb.ax.yaxis.get_ticklabels(), color=title_colour)
    for spine in ax3.spines.values():
        spine.set_visible(False)

    plt.tight_layout()
    return fig

# ════════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ════════════════════════════════════════════════════════════════════════════════

st.title("🏎️  F1 \"What If\" Race Simulator")
st.markdown(
    "Simulate any Bahrain-style race using real FastF1 data and "
    "XGBoost models trained on 2023–2025 seasons. "
    "Change strategy, safety car probability, or season — and see what happens."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    # Model path
    model_dir = st.text_input(
        "Model directory",
        value="./models",   # or wherever you put the .pkl files locally 
        help="Path to folder containing .pkl and .json model files"
    )

    st.divider()

    # Season + circuit
    season  = st.selectbox("Season", [2023, 2024, 2025], index=0,
                            help="Pace factors are derived from the first 5 races of this season")
    circuit = st.selectbox("Circuit", list(CIRCUITS.keys()), index=0)
    circ_cfg = CIRCUITS[circuit]

    st.divider()

    # Race conditions
    st.subheader("🌡️ Conditions")
    track_temp  = st.slider("Track temp (°C)", 15, 55,
                             int(circ_cfg["track_temp"]), step=1)
    air_temp    = st.slider("Air temp (°C)", 10, 45,
                             int(circ_cfg["air_temp"]), step=1)
    rainfall    = st.selectbox("Rainfall", ["Dry", "Wet"],
                                index=0) == "Wet"
    sc_prob     = st.slider("Safety car probability per lap",
                             0.0, 0.15, 0.04, step=0.01,
                             format="%.2f")

    st.divider()

    # Strategy editor
    st.subheader("🔧 Strategies")
    strategies = {}
    for entry in DEFAULT_GRID:
        drv = entry["driver"]
        with st.expander(f"{drv}"):
            default_s = DEFAULT_STRATEGIES[drv]
            pit1_lap  = st.number_input(f"Stop 1 — lap",  10, 45,
                                         default_s[0][0], key=f"{drv}_p1l")
            pit1_cmp  = st.selectbox(f"Stop 1 — compound",
                                      ["SOFT", "MEDIUM", "HARD"],
                                      index=default_s[0][1], key=f"{drv}_p1c")
            pit2_lap  = st.number_input(f"Stop 2 — lap",  25, 56,
                                         default_s[1][0], key=f"{drv}_p2l")
            pit2_cmp  = st.selectbox(f"Stop 2 — compound",
                                      ["SOFT", "MEDIUM", "HARD"],
                                      index=default_s[1][1], key=f"{drv}_p2c")
            strategies[drv] = [
                (int(pit1_lap), COMPOUND_MAP[pit1_cmp]),
                (int(pit2_lap), COMPOUND_MAP[pit2_cmp]),
            ]

    st.divider()

    # Monte Carlo runs
    n_runs = st.select_slider(
        "Simulations", options=[100, 250, 500, 1000], value=500
    )

    run_btn = st.button("🚀 Run Simulation", type="primary", use_container_width=True)

# ── Main panel ────────────────────────────────────────────────────────────────
if not run_btn:
    st.info(
        "👈 Configure the race in the sidebar and click **Run Simulation** to start."
    )
    st.markdown("""
    ### How it works
    1. **Pace factors** are derived from real FastF1 race data for the selected season
    2. The **lap time model** (XGBoost, Module 1) predicts each driver's lap time every lap
    3. The **overtake model** (XGBoost, Module 2) decides if a following car gets past
    4. The full race is simulated **N times** (Monte Carlo) — each run has different random noise
    5. Win probability = how often each driver wins across all N runs

    ### Valid seasons
    | Season | Era |
    |--------|-----|
    | 2023 | Red Bull dominant — VER won 19/22 races |
    | 2024 | McLaren / Red Bull / Ferrari close fight |
    | 2025 | McLaren dominant |
    """)

else:
    # Load models
    try:
        with st.spinner("Loading models..."):
            lap_model, ovt_model, team_encoder, _ = load_models(model_dir)
    except Exception as e:
        st.error(f"❌ Could not load models from `{model_dir}`: {e}")
        st.stop()

    # Derive pace factors
    with st.spinner(f"Deriving {season} pace factors from FastF1..."):
        try:
            import fastf1
            fastf1.Cache.enable_cache("./f1_cache")  # local cache folder
            pace_factors = calculate_pace_factors(season)
        except Exception as e:
            st.error(f"❌ Could not load FastF1 data: {e}")
            st.stop()

    # Build config + grid
    config = {
        "circuit": circuit,
        "total_laps": circ_cfg["total_laps"],
        "track_temp": track_temp,
        "air_temp": air_temp,
        "rainfall": int(rainfall),
        "sc_prob_per_lap": sc_prob,
        "pace_factors": pace_factors,
    }
    grid = []
    for i, entry in enumerate(DEFAULT_GRID):
        drv = entry["driver"]
        grid.append(DriverState(
            driver       = drv,
            team_encoded = encode_team(team_encoder, entry["team"]),
            team_name    = entry["team"],
            position     = i + 1,
            compound     = entry["compound"],
            tyre_age     = entry["tyre_age"],
            strategy     = strategies[drv],
        ))

    # Show pace factors
    with st.expander(f"📊 {season} pace factors (click to expand)"):
        pf_rows = sorted(pace_factors.items(), key=lambda x: x[1])
        pf_df = pd.DataFrame([
            {"Team": t, "Factor": f"{f:.4f}",
             "Gap per lap": f"+{(f-1)*95:.2f}s"}
            for t, f in pf_rows
        ])
        st.dataframe(pf_df, hide_index=True, use_container_width=True)

    # Monte Carlo
    st.subheader(f"🏎️  Running {n_runs:,} simulations...")
    probs = run_monte_carlo(config, grid, lap_model, ovt_model, n_runs)

    # Single race trace + overtake probs
    with st.spinner("Generating race trace..."):
        pos_history, ovt_probs = run_trace_race(config, grid, lap_model, ovt_model)

    # Results table
    st.subheader("📋 Results")
    results_df = pd.DataFrame([
        {"Driver": d, "Win Probability": f"{p*100:.1f}%",
         "Wins": int(p * n_runs)}
        for d, p in probs.items()
    ])
    st.dataframe(results_df, hide_index=True, use_container_width=True)

    # Charts
    st.subheader("📈 Visualisation")
    fig = plot_results(probs, pos_history, ovt_probs,
                       season, circuit, circ_cfg["total_laps"])
    st.pyplot(fig, use_container_width=True)

    # Download chart
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    st.download_button(
        "⬇️  Download chart as PNG",
        data=buf.getvalue(),
        file_name=f"f1_simulation_{season}_{circuit.lower()}.png",
        mime="image/png",
    )

    # Footer note
    st.caption(
        "⚠️ Valid for seasons 2023–2025 only (model training range). "
        "Changing season re-derives pace factors from real FastF1 data automatically."
    )