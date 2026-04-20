"""
Authoritative reference data for the 2026 and 2027 F1 seasons.
Injected into the Engineer Chat AI system prompt as ground truth.

To update for 2027: edit the data constants only — no logic changes needed.
"""

# ── MOM / DRS era boundary ────────────────────────────────────────────────────

SEASON_MOM_INTRODUCED = 2026


def uses_mom(year: int) -> bool:
    """Return True if the session year uses MOM instead of DRS."""
    return year >= SEASON_MOM_INTRODUCED

# ── 2026 Drivers ──────────────────────────────────────────────────────────────

DRIVERS_2026 = {
    "HAM": {"full_name": "Lewis Hamilton",    "number": 44, "team": "Ferrari",       "nationality": "British"},
    "LEC": {"full_name": "Charles Leclerc",   "number": 16, "team": "Ferrari",       "nationality": "Monégasque"},
    "NOR": {"full_name": "Lando Norris",      "number":  4, "team": "McLaren",       "nationality": "British"},
    "PIA": {"full_name": "Oscar Piastri",     "number": 81, "team": "McLaren",       "nationality": "Australian"},
    "RUS": {"full_name": "George Russell",    "number": 63, "team": "Mercedes",      "nationality": "British"},
    "ANT": {"full_name": "Kimi Antonelli",    "number": 12, "team": "Mercedes",      "nationality": "Italian"},
    "VER": {"full_name": "Max Verstappen",    "number":  1, "team": "Red Bull",      "nationality": "Dutch"},
    "HAD": {"full_name": "Isack Hadjar",      "number":  6, "team": "Red Bull",      "nationality": "French"},
    "SAI": {"full_name": "Carlos Sainz",      "number": 55, "team": "Williams",      "nationality": "Spanish"},
    "ALB": {"full_name": "Alex Albon",        "number": 23, "team": "Williams",      "nationality": "Thai-British"},
    "ALO": {"full_name": "Fernando Alonso",   "number": 14, "team": "Aston Martin",  "nationality": "Spanish"},
    "STR": {"full_name": "Lance Stroll",      "number": 18, "team": "Aston Martin",  "nationality": "Canadian"},
    "GAS": {"full_name": "Pierre Gasly",      "number": 10, "team": "Alpine",        "nationality": "French"},
    "COL": {"full_name": "Franco Colapinto",  "number": 43, "team": "Alpine",        "nationality": "Argentine"},
    "OCO": {"full_name": "Esteban Ocon",      "number": 31, "team": "Haas",          "nationality": "French"},
    "BEA": {"full_name": "Oliver Bearman",    "number": 87, "team": "Haas",          "nationality": "British"},
    "LAW": {"full_name": "Liam Lawson",       "number": 30, "team": "Racing Bulls",  "nationality": "New Zealander"},
    "LIN": {"full_name": "Arvid Lindblad",    "number": 41, "team": "Racing Bulls",  "nationality": "British-Swedish"},
    "HUL": {"full_name": "Nico Hulkenberg",   "number": 27, "team": "Audi",          "nationality": "German"},
    "BOR": {"full_name": "Gabriel Bortoleto", "number":  5, "team": "Audi",          "nationality": "Brazilian"},
    "PER": {"full_name": "Sergio Perez",      "number": 11, "team": "Cadillac",      "nationality": "Mexican"},
    "BOT": {"full_name": "Valtteri Bottas",   "number": 77, "team": "Cadillac",      "nationality": "Finnish"},
}

# ── 2026 Teams ────────────────────────────────────────────────────────────────

TEAMS_2026 = {
    "Ferrari":       {"power_unit": "Ferrari PU",       "principal": "Frederic Vasseur"},
    "McLaren":       {"power_unit": "Mercedes PU",      "principal": "Andrea Stella"},
    "Mercedes":      {"power_unit": "Mercedes PU",      "principal": "Toto Wolff"},
    "Red Bull":      {"power_unit": "Honda RBPT PU",    "principal": "Christian Horner"},
    "Williams":      {"power_unit": "Mercedes PU",      "principal": "James Vowles"},
    "Aston Martin":  {"power_unit": "Honda RBPT PU",    "principal": "Andy Cowell"},
    "Alpine":        {"power_unit": "Renault PU",       "principal": "Oliver Oakes"},
    "Haas":          {"power_unit": "Ferrari PU",       "principal": "Ayao Komatsu"},
    "Racing Bulls":  {"power_unit": "Honda RBPT PU",    "principal": "Laurent Mekies"},
    "Audi":          {"power_unit": "Audi PU",          "principal": "Mattia Binotto"},
    "Cadillac":      {"power_unit": "Ferrari PU",       "principal": "Graeme Lowdon"},
}

# ── 2026 Calendar ─────────────────────────────────────────────────────────────

CIRCUITS_2026 = [
    {"round":  1, "name": "Bahrain Grand Prix",               "circuit": "Bahrain International Circuit",          "country": "Bahrain",        "laps": 57, "length_km": 5.412},
    {"round":  2, "name": "Saudi Arabian Grand Prix",         "circuit": "Jeddah Corniche Circuit",                "country": "Saudi Arabia",   "laps": 50, "length_km": 6.174},
    {"round":  3, "name": "Australian Grand Prix",            "circuit": "Albert Park Circuit",                    "country": "Australia",      "laps": 58, "length_km": 5.278},
    {"round":  4, "name": "Japanese Grand Prix",              "circuit": "Suzuka International Racing Course",     "country": "Japan",          "laps": 53, "length_km": 5.807},
    {"round":  5, "name": "Chinese Grand Prix",               "circuit": "Shanghai International Circuit",         "country": "China",          "laps": 56, "length_km": 5.451},
    {"round":  6, "name": "Miami Grand Prix",                 "circuit": "Miami International Autodrome",          "country": "USA",            "laps": 57, "length_km": 5.412},
    {"round":  7, "name": "Emilia Romagna Grand Prix",        "circuit": "Autodromo Enzo e Dino Ferrari",          "country": "Italy",          "laps": 63, "length_km": 4.909},
    {"round":  8, "name": "Monaco Grand Prix",                "circuit": "Circuit de Monaco",                      "country": "Monaco",         "laps": 78, "length_km": 3.337},
    {"round":  9, "name": "Spanish Grand Prix",               "circuit": "Circuit de Barcelona-Catalunya",         "country": "Spain",          "laps": 66, "length_km": 4.657},
    {"round": 10, "name": "Canadian Grand Prix",              "circuit": "Circuit Gilles Villeneuve",              "country": "Canada",         "laps": 70, "length_km": 4.361},
    {"round": 11, "name": "Austrian Grand Prix",              "circuit": "Red Bull Ring",                          "country": "Austria",        "laps": 71, "length_km": 4.318},
    {"round": 12, "name": "British Grand Prix",               "circuit": "Silverstone Circuit",                    "country": "UK",             "laps": 52, "length_km": 5.891},
    {"round": 13, "name": "Belgian Grand Prix",               "circuit": "Circuit de Spa-Francorchamps",           "country": "Belgium",        "laps": 44, "length_km": 7.004},
    {"round": 14, "name": "Hungarian Grand Prix",             "circuit": "Hungaroring",                            "country": "Hungary",        "laps": 70, "length_km": 4.381},
    {"round": 15, "name": "Dutch Grand Prix",                 "circuit": "Circuit Zandvoort",                      "country": "Netherlands",    "laps": 72, "length_km": 4.259},
    {"round": 16, "name": "Italian Grand Prix",               "circuit": "Autodromo Nazionale Monza",              "country": "Italy",          "laps": 53, "length_km": 5.793},
    {"round": 17, "name": "Azerbaijan Grand Prix",            "circuit": "Baku City Circuit",                      "country": "Azerbaijan",     "laps": 51, "length_km": 6.003},
    {"round": 18, "name": "Singapore Grand Prix",             "circuit": "Marina Bay Street Circuit",              "country": "Singapore",      "laps": 62, "length_km": 4.940},
    {"round": 19, "name": "United States Grand Prix",         "circuit": "Circuit of the Americas",                "country": "USA",            "laps": 56, "length_km": 5.513},
    {"round": 20, "name": "Mexico City Grand Prix",           "circuit": "Autodromo Hermanos Rodriguez",           "country": "Mexico",         "laps": 71, "length_km": 4.304},
    {"round": 21, "name": "São Paulo Grand Prix",             "circuit": "Autodromo Jose Carlos Pace",             "country": "Brazil",         "laps": 71, "length_km": 4.309},
    {"round": 22, "name": "Las Vegas Grand Prix",             "circuit": "Las Vegas Street Circuit",               "country": "USA",            "laps": 50, "length_km": 6.201},
    {"round": 23, "name": "Qatar Grand Prix",                 "circuit": "Lusail International Circuit",           "country": "Qatar",          "laps": 57, "length_km": 5.380},
    {"round": 24, "name": "Abu Dhabi Grand Prix",             "circuit": "Yas Marina Circuit",                     "country": "UAE",            "laps": 58, "length_km": 5.281},
]

# ── 2026 Technical Regulations ────────────────────────────────────────────────

REGULATIONS_2026 = [
    "New power unit regulations introduced in 2026.",
    "50/50 split between internal combustion and electrical power output.",
    "Simplified aerodynamic regulations to reduce dirty air effect and improve racing.",
    "Active aerodynamics reintroduced — moveable front and rear wings.",
    "Reduced car weight targets compared to the 2022–2025 regulation era.",
    "New Pirelli tyre compounds introduced specifically for 2026 regulations.",
    "11 constructors on the grid for the first time, with Cadillac (formerly Andretti) joining.",
    "Audi (formerly Alfa Romeo/Sauber) now competing as a full works team.",
    # MOM replaces DRS from 2026
    "DRS (Drag Reduction System) is ABOLISHED from 2026. It does not exist in 2026 or later seasons.",
    "Overtaking aid from 2026 is MOM — Manual Override Mode (also called Overtake Mode).",
    "MOM is an electrical power boost from the MGU-K, not a wing-opening mechanism.",
    "MOM is available when a driver is within 1 second of the car ahead at a detection point.",
    "MOM delivers up to 350 kW of additional electrical power.",
    "MOM is sustained up to a maximum speed of 337 km/h.",
    "MOM allows an additional 0.5 MJ of energy recovery per lap.",
    "MOM is disabled for the first 2 laps of the race and after any safety car restart.",
]

# ── 2027 Drivers (PROVISIONAL — subject to change) ───────────────────────────

DRIVERS_2027 = {
    # PROVISIONAL — only confirmed signings as of early 2026; unconfirmed seats marked TBC
    "HAM": {"full_name": "Lewis Hamilton",    "number": 44, "team": "Ferrari",       "status": "confirmed"},
    "LEC": {"full_name": "Charles Leclerc",   "number": 16, "team": "Ferrari",       "status": "confirmed"},
    "NOR": {"full_name": "Lando Norris",      "number":  4, "team": "McLaren",       "status": "confirmed"},
    "PIA": {"full_name": "Oscar Piastri",     "number": 81, "team": "McLaren",       "status": "confirmed"},
    "RUS": {"full_name": "George Russell",    "number": 63, "team": "Mercedes",      "status": "confirmed"},
    "ANT": {"full_name": "Kimi Antonelli",    "number": 12, "team": "Mercedes",      "status": "confirmed"},
    "VER": {"full_name": "Max Verstappen",    "number":  1, "team": "Red Bull",      "status": "confirmed"},
    "HAD": {"full_name": "Isack Hadjar",      "number":  6, "team": "Red Bull",      "status": "confirmed"},
    "SAI": {"full_name": "Carlos Sainz",      "number": 55, "team": "Williams",      "status": "confirmed"},
    "ALB": {"full_name": "Alex Albon",        "number": 23, "team": "Williams",      "status": "confirmed"},
    "ALO": {"full_name": "Fernando Alonso",   "number": 14, "team": "Aston Martin",  "status": "confirmed"},
    "STR": {"full_name": "Lance Stroll",      "number": 18, "team": "Aston Martin",  "status": "confirmed"},
    "TBC_ALP1": {"full_name": "TBC",          "number":  0, "team": "Alpine",        "status": "unconfirmed"},
    "TBC_ALP2": {"full_name": "TBC",          "number":  0, "team": "Alpine",        "status": "unconfirmed"},
    "TBC_HAS1": {"full_name": "TBC",          "number":  0, "team": "Haas",          "status": "unconfirmed"},
    "TBC_HAS2": {"full_name": "TBC",          "number":  0, "team": "Haas",          "status": "unconfirmed"},
    "LAW": {"full_name": "Liam Lawson",       "number": 30, "team": "Racing Bulls",  "status": "confirmed"},
    "LIN": {"full_name": "Arvid Lindblad",    "number": 41, "team": "Racing Bulls",  "status": "confirmed"},
    "HUL": {"full_name": "Nico Hulkenberg",   "number": 27, "team": "Audi",          "status": "confirmed"},
    "BOR": {"full_name": "Gabriel Bortoleto", "number":  5, "team": "Audi",          "status": "confirmed"},
    "TBC_CAD1": {"full_name": "TBC",          "number":  0, "team": "Cadillac",      "status": "unconfirmed"},
    "TBC_CAD2": {"full_name": "TBC",          "number":  0, "team": "Cadillac",      "status": "unconfirmed"},
}


def build_season_context(year: int) -> str:
    """
    Returns a formatted string of season data for injection into an AI system prompt.
    Covers driver-team pairings, key regulations, and a note on circuit availability.
    """
    if year == 2026:
        drivers = DRIVERS_2026
        teams = TEAMS_2026
        regulations = REGULATIONS_2026
        provisional_note = ""
    elif year == 2027:
        drivers = DRIVERS_2027
        teams = TEAMS_2026  # Teams largely unchanged; update when confirmed
        regulations = REGULATIONS_2026  # Placeholder until 2027 regs confirmed
        provisional_note = "\nNOTE: 2027 driver lineup is PROVISIONAL. Unconfirmed seats are marked TBC.\n"
    else:
        return f"No season data available for {year}."

    lines = [f"=== {year} F1 SEASON REFERENCE DATA (ground truth — override training data) ==="]

    if provisional_note:
        lines.append(provisional_note)

    lines.append(f"\n{year} DRIVER-TEAM PAIRINGS:")
    for code, d in drivers.items():
        if d["full_name"] == "TBC":
            continue
        team = d["team"]
        team_info = teams.get(team, {})
        pu = team_info.get("power_unit", "")
        lines.append(
            f"  #{d['number']:>2}  {d['full_name']:<22} ({code})  —  {team}  [{pu}]"
        )

    lines.append(f"\n{year} CONSTRUCTOR PRINCIPALS:")
    for team, info in teams.items():
        lines.append(f"  {team:<14} — TP: {info['principal']:<22} PU: {info['power_unit']}")

    lines.append(f"\n{year} KEY TECHNICAL REGULATIONS:")
    for reg in regulations:
        lines.append(f"  - {reg}")

    lines.append(
        f"\nCIRCUIT DATA: Full {year} calendar ({len(CIRCUITS_2026)} rounds) is available. "
        "Ask about a specific circuit or round for details."
    )

    lines.append("\n=== END SEASON REFERENCE DATA ===")

    return "\n".join(lines)
