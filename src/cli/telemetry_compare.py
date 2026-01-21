"""
CLI interface for telemetry comparison feature.

Allows users to select two laps (driver/lap combinations) and generate
a comparative telemetry chart showing Speed, Throttle/Brake, and Delta Time.
"""

import sys
import os
from typing import Optional
from questionary import Style, select, Choice, checkbox
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.f1_data import (
    get_race_weekends_by_year,
    load_session,
    enable_cache,
    get_driver_colors,
)
from src.compare import (
    create_telemetry_comparison,
    show_comparison_chart,
    extract_lap_telemetry_from_frames,
)
from src.lib.time import format_time


# CLI styling matching the existing race_selection.py
STYLE = Style([
    ("pointer", "fg:#e10600 bold"),
    ("selected", "noinherit fg:#64eb34 bold"),
    ("highlighted", "fg:#e10600 bold"),
    ("answer", "fg:#64eb34 bold")
])


def get_driver_laps(session, driver_code: str):
    """
    Get list of available laps for a specific driver.
    
    Returns a list of dicts with lap number and lap time.
    """
    driver_laps = session.laps.pick_drivers(driver_code)
    laps_info = []
    
    for _, lap in driver_laps.iterrows():
        lap_num = int(lap['LapNumber'])
        lap_time = lap.get('LapTime')
        
        if lap_time is not None and hasattr(lap_time, 'total_seconds'):
            lap_time_str = format_time(lap_time.total_seconds())
        else:
            lap_time_str = "N/A"
        
        laps_info.append({
            'lap_number': lap_num,
            'lap_time_str': lap_time_str,
            'lap_time': lap_time.total_seconds() if lap_time is not None and hasattr(lap_time, 'total_seconds') else None,
            'compound': str(lap.get('Compound', 'UNKNOWN')),
        })
    
    return sorted(laps_info, key=lambda x: x['lap_number'])


def get_lap_telemetry(session, driver_code: str, lap_number: int):
    """
    Extract telemetry data for a specific driver's lap.
    
    Returns a dict with telemetry arrays.
    """
    import numpy as np
    
    driver_laps = session.laps.pick_drivers(driver_code)
    lap = driver_laps[driver_laps['LapNumber'] == lap_number]
    
    if lap.empty:
        raise ValueError(f"Lap {lap_number} not found for driver {driver_code}")
    
    lap = lap.iloc[0]
    telemetry = lap.get_telemetry()
    
    if telemetry is None or telemetry.empty:
        raise ValueError(f"No telemetry data for {driver_code} lap {lap_number}")
    
    return {
        't': telemetry['Time'].dt.total_seconds().to_numpy(),
        'dist': telemetry['Distance'].to_numpy(),
        'speed': telemetry['Speed'].to_numpy(),
        'throttle': telemetry['Throttle'].to_numpy(),
        'brake': telemetry['Brake'].to_numpy() * 100.0,  # Normalize to 0-100
        'gear': telemetry['nGear'].to_numpy(),
        'drs': telemetry['DRS'].to_numpy() if 'DRS' in telemetry.columns else np.zeros(len(telemetry)),
    }


def rgb_to_matplotlib(rgb_tuple):
    """Convert 0-255 RGB tuple to 0-1 matplotlib format."""
    return tuple(c / 255.0 for c in rgb_tuple)


def cli_compare():
    """
    Interactive CLI for telemetry comparison.
    
    Guides user through:
    1. Year selection
    2. Round selection
    3. Session type selection
    4. Driver 1 + Lap selection
    5. Driver 2 + Lap selection
    6. Chart generation
    """
    console = Console()
    console.print(Markdown("# F1 Telemetry Comparison 📊"))
    console.print(Markdown("Compare lap telemetry between two drivers or laps\n"))
    
    enable_cache()
    
    # === Year Selection ===
    current_year = 2025
    years = [str(year) for year in range(current_year, 2018, -1)]  # FastF1 has good data from 2018+
    year = select("Choose a year", choices=years, qmark="🗓️ ", style=STYLE).ask()
    if not year:
        sys.exit(0)
    year = int(year)
    
    # === Round Selection ===
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn("[bold]Loading race schedule…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        weekends = get_race_weekends_by_year(year)
    
    rounds = [
        Choice(title=f"{row['event_name']} ({row['date']})", value=row['round_number'])
        for row in weekends
    ]
    round_number = select("Choose a round", choices=rounds, qmark="🌏 ", style=STYLE).ask()
    if not round_number:
        sys.exit(0)
    
    # === Session Type Selection ===
    session_choices = [
        Choice(title="Race", value="R"),
        Choice(title="Qualifying", value="Q"),
    ]
    # Check if sprint weekend
    for row in weekends:
        if row['round_number'] == round_number and 'sprint' in row['type']:
            session_choices.insert(0, Choice(title="Sprint Qualifying", value="SQ"))
            session_choices.insert(1, Choice(title="Sprint", value="S"))
            break
    
    session_type = select("Choose a session", choices=session_choices, qmark="🏁 ", style=STYLE).ask()
    if not session_type:
        sys.exit(0)
    
    # === Load Session ===
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn("[bold]Loading session data (this may take a minute)…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        session = load_session(year, round_number, session_type)
    
    # Get driver info
    drivers = session.drivers
    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}
    driver_names = {num: session.get_driver(num).get("FullName", driver_codes[num]) for num in drivers}
    driver_colors = get_driver_colors(session)
    
    console.print(f"\n[bold green]Loaded:[/] {session.event['EventName']} - {session_type}\n")
    
    # === Driver 1 Selection ===
    console.print(Markdown("### Select First Lap"))
    
    driver1_choices = [
        Choice(title=f"{driver_codes[num]} - {driver_names[num]}", value=driver_codes[num])
        for num in drivers
    ]
    driver1_code = select("Select Driver 1", choices=driver1_choices, qmark="🏎️ ", style=STYLE).ask()
    if not driver1_code:
        sys.exit(0)
    
    # Get laps for driver 1
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn(f"[bold]Loading laps for {driver1_code}…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        driver1_laps = get_driver_laps(session, driver1_code)
    
    if not driver1_laps:
        console.print(f"[red]No laps found for {driver1_code}[/]")
        sys.exit(1)
    
    lap1_choices = [
        Choice(
            title=f"Lap {lap['lap_number']:2d} | {lap['lap_time_str']} | {lap['compound']}",
            value=lap['lap_number']
        )
        for lap in driver1_laps
    ]
    lap1_number = select(f"Select lap for {driver1_code}", choices=lap1_choices, qmark="🔢 ", style=STYLE).ask()
    if not lap1_number:
        sys.exit(0)
    
    # Get lap time for label
    lap1_info = next((lap for lap in driver1_laps if lap['lap_number'] == lap1_number), None)
    lap1_time = lap1_info['lap_time'] if lap1_info else None
    
    # === Driver 2 Selection ===
    console.print(Markdown("\n### Select Second Lap"))
    
    comparison_type = select(
        "Compare against",
        choices=[
            Choice(title="Different driver", value="different"),
            Choice(title="Same driver (different lap)", value="same"),
        ],
        qmark="🔄 ",
        style=STYLE
    ).ask()
    if not comparison_type:
        sys.exit(0)
    
    if comparison_type == "different":
        # Filter out driver 1 from choices
        driver2_choices = [
            Choice(title=f"{driver_codes[num]} - {driver_names[num]}", value=driver_codes[num])
            for num in drivers if driver_codes[num] != driver1_code
        ]
        driver2_code = select("Select Driver 2", choices=driver2_choices, qmark="🏎️ ", style=STYLE).ask()
        if not driver2_code:
            sys.exit(0)
    else:
        driver2_code = driver1_code
    
    # Get laps for driver 2
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn(f"[bold]Loading laps for {driver2_code}…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("load", total=None)
        driver2_laps = get_driver_laps(session, driver2_code)
    
    if not driver2_laps:
        console.print(f"[red]No laps found for {driver2_code}[/]")
        sys.exit(1)
    
    # Filter out lap 1 if same driver
    if comparison_type == "same":
        driver2_laps = [lap for lap in driver2_laps if lap['lap_number'] != lap1_number]
    
    if not driver2_laps:
        console.print(f"[red]No other laps available for {driver2_code}[/]")
        sys.exit(1)
    
    lap2_choices = [
        Choice(
            title=f"Lap {lap['lap_number']:2d} | {lap['lap_time_str']} | {lap['compound']}",
            value=lap['lap_number']
        )
        for lap in driver2_laps
    ]
    lap2_number = select(f"Select lap for {driver2_code}", choices=lap2_choices, qmark="🔢 ", style=STYLE).ask()
    if not lap2_number:
        sys.exit(0)
    
    # Get lap time for label
    lap2_info = next((lap for lap in driver2_laps if lap['lap_number'] == lap2_number), None)
    lap2_time = lap2_info['lap_time'] if lap2_info else None
    
    # === Output Options ===
    output_choice = select(
        "Output option",
        choices=[
            Choice(title="Display chart", value="display"),
            Choice(title="Save to file", value="save"),
            Choice(title="Both", value="both"),
        ],
        qmark="💾 ",
        style=STYLE
    ).ask()
    if not output_choice:
        sys.exit(0)
    
    # === Generate Comparison ===
    console.print(Markdown("\n### Generating Telemetry Comparison..."))
    
    with Progress(
        SpinnerColumn(style="bold red"),
        TextColumn("[bold]Extracting telemetry data…"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("extract", total=None)
        
        # Extract telemetry for both laps
        try:
            telemetry1 = get_lap_telemetry(session, driver1_code, lap1_number)
            telemetry2 = get_lap_telemetry(session, driver2_code, lap2_number)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/]")
            sys.exit(1)
        
        # Get colors
        color1 = rgb_to_matplotlib(driver_colors.get(driver1_code, (0, 200, 100)))
        color2 = rgb_to_matplotlib(driver_colors.get(driver2_code, (200, 50, 50)))
        
        # Create comparison
        label1 = f"{driver1_code} Lap {lap1_number}"
        label2 = f"{driver2_code} Lap {lap2_number}"
        
        comparison = create_telemetry_comparison(
            telemetry1, telemetry2,
            label1=label1, label2=label2,
            color1=color1, color2=color2,
            lap_time1=lap1_time, lap_time2=lap2_time,
        )
    
    # Generate chart title
    event_name = session.event['EventName']
    session_name = {'R': 'Race', 'Q': 'Qualifying', 'S': 'Sprint', 'SQ': 'Sprint Qualifying'}[session_type]
    chart_title = f"{year} {event_name} - {session_name}\n{label1} vs {label2}"
    
    # Display summary
    console.print("\n")
    table = Table(title="Comparison Summary", show_header=True)
    table.add_column("", style="bold")
    table.add_column(label1, style="green")
    table.add_column(label2, style="red")
    
    time1_str = format_time(lap1_time) if lap1_time else "N/A"
    time2_str = format_time(lap2_time) if lap2_time else "N/A"
    table.add_row("Lap Time", time1_str, time2_str)
    
    delta = comparison.delta_time[-1] if len(comparison.delta_time) > 0 else 0
    delta_str = f"{'+' if delta > 0 else ''}{delta:.3f}s"
    table.add_row("Delta", "Reference", delta_str)
    
    console.print(table)
    console.print("\n")
    
    # Save and/or display
    save_path = None
    if output_choice in ("save", "both"):
        # Generate filename
        safe_event = event_name.replace(" ", "_").replace("/", "-")
        filename = f"{year}_{safe_event}_{session_type}_{driver1_code}_L{lap1_number}_vs_{driver2_code}_L{lap2_number}.png"
        save_path = os.path.join("comparison_charts", filename)
        
        # Create directory if needed
        os.makedirs("comparison_charts", exist_ok=True)
    
    if output_choice == "save":
        show_comparison_chart(comparison, title=chart_title, save_path=save_path)
        console.print(f"[green]Chart saved to:[/] {save_path}")
    elif output_choice == "display":
        console.print("[dim]Opening chart window...[/]")
        show_comparison_chart(comparison, title=chart_title)
    else:  # both
        show_comparison_chart(comparison, title=chart_title, save_path=save_path)
        console.print(f"[green]Chart saved to:[/] {save_path}")
        console.print("[dim]Opening chart window...[/]")
        show_comparison_chart(comparison, title=chart_title)
    
    console.print("\n[bold green]Done![/]")


def cli_compare_quick(
    year: int,
    round_number: int,
    session_type: str,
    driver1: str,
    lap1: int,
    driver2: str,
    lap2: int,
    save_path: Optional[str] = None,
):
    """
    Quick comparison function for command-line arguments.
    
    Args:
        year: Season year
        round_number: Round number
        session_type: 'R', 'Q', 'S', or 'SQ'
        driver1: First driver code (e.g., 'VER')
        lap1: First lap number
        driver2: Second driver code (e.g., 'HAM')
        lap2: Second lap number
        save_path: Optional path to save the chart
    """
    console = Console()
    enable_cache()
    
    console.print(f"[bold]Loading {year} Round {round_number} {session_type}...[/]")
    session = load_session(year, round_number, session_type)
    
    console.print(f"[bold]Extracting telemetry for {driver1} L{lap1} vs {driver2} L{lap2}...[/]")
    
    telemetry1 = get_lap_telemetry(session, driver1, lap1)
    telemetry2 = get_lap_telemetry(session, driver2, lap2)
    
    driver_colors = get_driver_colors(session)
    color1 = rgb_to_matplotlib(driver_colors.get(driver1, (0, 200, 100)))
    color2 = rgb_to_matplotlib(driver_colors.get(driver2, (200, 50, 50)))
    
    # Get lap times
    driver1_laps = get_driver_laps(session, driver1)
    driver2_laps = get_driver_laps(session, driver2)
    lap1_info = next((lap for lap in driver1_laps if lap['lap_number'] == lap1), None)
    lap2_info = next((lap for lap in driver2_laps if lap['lap_number'] == lap2), None)
    
    comparison = create_telemetry_comparison(
        telemetry1, telemetry2,
        label1=f"{driver1} Lap {lap1}",
        label2=f"{driver2} Lap {lap2}",
        color1=color1, color2=color2,
        lap_time1=lap1_info['lap_time'] if lap1_info else None,
        lap_time2=lap2_info['lap_time'] if lap2_info else None,
    )
    
    event_name = session.event['EventName']
    session_name = {'R': 'Race', 'Q': 'Qualifying', 'S': 'Sprint', 'SQ': 'Sprint Qualifying'}[session_type]
    chart_title = f"{year} {event_name} - {session_name}"
    
    show_comparison_chart(comparison, title=chart_title, save_path=save_path)
    
    if save_path:
        console.print(f"[green]Chart saved to:[/] {save_path}")


if __name__ == "__main__":
    cli_compare()
