from questionary import Style, select, Choice
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from src.f1_data import get_race_weekends_by_year
import sys
import os
import subprocess
from src.lib.season import get_season

def cli_load():
    current_year = get_season()

    style = Style([
        ("pointer", "fg:#e10600 bold"),
        ("selected", "noinherit fg:#64eb34 bold"),
        ("highlighted", "fg:#e10600 bold"),
        ("answer", "fg:#64eb34 bold")
    ])

    console = Console()
    console.print(Markdown("# F1 Race Replay 🏎️"))

    years = [str(year) for year in range(current_year, 2009, -1)]
    year = select("Choose a year", choices=years, qmark="🗓️ ", style=style).ask()
    if not year:
        sys.exit(0)
    else:
        year = int(year)
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn("[bold]Loading races…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        data = get_race_weekends_by_year(year)

    rounds = [Choice(title=f"{row['event_name']} ({row['date']})",value=row['round_number']) for row in data]
    round_number = select("Choose a round", choices=rounds, qmark="🌏", style=style).ask()
    if not round_number:
        sys.exit(0)

    sessions = ["Qualifying", "Race"]
    for row in data:
        if row['round_number'] == round_number:
            if row['type'].find('sprint') != -1:
                sessions.insert(0, "Sprint Qualifying")
                sessions.insert(1, "Sprint")
    session = select("Choose a session", choices=sessions, qmark="🏁", style=style).ask()
    if not session:
        sys.exit(0)
        
    if session in ("Sprint", "Race"):
        HUD = [Choice(title="Yes", value=True), Choice(title="No", value=False)]
        hud = select("HUD?", choices=HUD, qmark="🖥️ ", style=style).ask()
        if hud is None:
            sys.exit(0)
    else:
        hud = True

    flag = None
    match session:
        case "Qualifying":
            flag = "--qualifying" 
        case "Sprint Qualifying":
            flag = "--sprint-qualifying"  
        case "Sprint":
            flag = "--sprint"     
    main_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'main.py'))
    cmd = [sys.executable, main_path, "--viewer"]
    if year is not None:
        cmd += ["--year", str(year)]
    if round_number is not None:
        cmd += ["--round", str(round_number)]
    if flag:
        cmd.append(flag)
    if not hud:
        cmd.append("--no-hud")
    if "--verbose" in sys.argv:
        cmd.append("--verbose")
    subprocess.run(cmd)
