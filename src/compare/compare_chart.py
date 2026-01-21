"""
Matplotlib chart generation for telemetry comparison.

Creates multi-panel charts comparing Speed, Throttle/Brake, and Delta Time
between two laps, indexed by track distance.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from typing import Optional, Tuple, List

from .telemetry_compare import TelemetryComparison


# F1-inspired dark theme colors
BACKGROUND_COLOR = '#1a1a1a'
GRID_COLOR = '#333333'
TEXT_COLOR = '#ffffff'
AXIS_COLOR = '#666666'
POSITIVE_DELTA_COLOR = '#ff4444'  # Red - lap2 is slower
NEGATIVE_DELTA_COLOR = '#44ff44'  # Green - lap2 is faster


def setup_dark_style():
    """Configure matplotlib for F1-style dark theme."""
    plt.rcParams.update({
        'figure.facecolor': BACKGROUND_COLOR,
        'axes.facecolor': BACKGROUND_COLOR,
        'axes.edgecolor': AXIS_COLOR,
        'axes.labelcolor': TEXT_COLOR,
        'axes.titlecolor': TEXT_COLOR,
        'xtick.color': TEXT_COLOR,
        'ytick.color': TEXT_COLOR,
        'text.color': TEXT_COLOR,
        'grid.color': GRID_COLOR,
        'grid.alpha': 0.5,
        'legend.facecolor': '#2a2a2a',
        'legend.edgecolor': AXIS_COLOR,
        'legend.labelcolor': TEXT_COLOR,
        'font.family': 'sans-serif',
        'font.size': 10,
    })


def create_comparison_chart(
    comparison: TelemetryComparison,
    title: Optional[str] = None,
    figsize: Tuple[float, float] = (14, 10),
    show_gear: bool = False,
    show_drs: bool = True,
    drs_zones: Optional[List[dict]] = None,
) -> Tuple[Figure, List[Axes]]:
    """
    Create a multi-panel comparison chart.
    
    The chart contains:
    - Panel 1: Speed comparison (km/h)
    - Panel 2: Throttle & Brake comparison (stacked)
    - Panel 3: Delta Time (cumulative time difference)
    
    Args:
        comparison: TelemetryComparison object with aligned data
        title: Chart title (auto-generated if None)
        figsize: Figure size (width, height) in inches
        show_gear: Whether to overlay gear numbers on speed panel
        show_drs: Whether to highlight DRS activation zones
        drs_zones: Optional list of DRS zone definitions
        
    Returns:
        Tuple of (Figure, list of Axes)
    """
    setup_dark_style()
    
    # Create figure with constrained layout for proper spacing
    fig = plt.figure(figsize=figsize, constrained_layout=True)
    
    # Create grid: 3 rows with different heights
    gs = gridspec.GridSpec(3, 1, figure=fig, height_ratios=[3, 2, 2])
    
    ax_speed = fig.add_subplot(gs[0])
    ax_inputs = fig.add_subplot(gs[1], sharex=ax_speed)
    ax_delta = fig.add_subplot(gs[2], sharex=ax_speed)
    
    axes = [ax_speed, ax_inputs, ax_delta]
    
    # Convert distance to km for better readability
    dist_km = comparison.distance / 1000.0
    
    # === Panel 1: Speed ===
    ax_speed.plot(
        dist_km, comparison.lap1_speed,
        color=comparison.lap1_color, linewidth=1.5,
        label=comparison.lap1_label, alpha=0.9
    )
    ax_speed.plot(
        dist_km, comparison.lap2_speed,
        color=comparison.lap2_color, linewidth=1.5,
        label=comparison.lap2_label, alpha=0.9
    )
    
    ax_speed.set_ylabel('Speed (km/h)', fontsize=11, fontweight='bold')
    ax_speed.legend(loc='upper right', fontsize=9)
    ax_speed.grid(True, alpha=0.3)
    ax_speed.set_ylim(bottom=0)
    
    # Add DRS zone highlights
    if show_drs:
        _add_drs_highlights(ax_speed, comparison, dist_km)
    
    # === Panel 2: Throttle & Brake ===
    # Throttle (positive, going up)
    ax_inputs.fill_between(
        dist_km, 0, comparison.lap1_throttle,
        alpha=0.3, color=comparison.lap1_color, linewidth=0
    )
    ax_inputs.fill_between(
        dist_km, 0, comparison.lap2_throttle,
        alpha=0.3, color=comparison.lap2_color, linewidth=0
    )
    ax_inputs.plot(
        dist_km, comparison.lap1_throttle,
        color=comparison.lap1_color, linewidth=1.2, alpha=0.8
    )
    ax_inputs.plot(
        dist_km, comparison.lap2_throttle,
        color=comparison.lap2_color, linewidth=1.2, alpha=0.8
    )
    
    # Brake (negative, going down) - shown as negative values
    brake1_neg = -comparison.lap1_brake
    brake2_neg = -comparison.lap2_brake
    ax_inputs.fill_between(
        dist_km, 0, brake1_neg,
        alpha=0.3, color=comparison.lap1_color, linewidth=0
    )
    ax_inputs.fill_between(
        dist_km, 0, brake2_neg,
        alpha=0.3, color=comparison.lap2_color, linewidth=0
    )
    ax_inputs.plot(
        dist_km, brake1_neg,
        color=comparison.lap1_color, linewidth=1.2, alpha=0.8, linestyle='--'
    )
    ax_inputs.plot(
        dist_km, brake2_neg,
        color=comparison.lap2_color, linewidth=1.2, alpha=0.8, linestyle='--'
    )
    
    ax_inputs.axhline(y=0, color=AXIS_COLOR, linewidth=0.5)
    ax_inputs.set_ylabel('Throttle / Brake (%)', fontsize=11, fontweight='bold')
    ax_inputs.set_ylim(-105, 105)
    ax_inputs.grid(True, alpha=0.3)
    
    # Add labels for throttle/brake regions
    ax_inputs.text(
        0.02, 0.95, 'THROTTLE ↑', transform=ax_inputs.transAxes,
        fontsize=8, alpha=0.6, va='top'
    )
    ax_inputs.text(
        0.02, 0.05, 'BRAKE ↓', transform=ax_inputs.transAxes,
        fontsize=8, alpha=0.6, va='bottom'
    )
    
    # === Panel 3: Delta Time ===
    delta = comparison.delta_time
    
    # Create filled areas for positive/negative delta
    positive_mask = list(delta >= 0)
    negative_mask = list(delta < 0)
    
    ax_delta.fill_between(
        dist_km, 0, delta,
        where=positive_mask,
        color=POSITIVE_DELTA_COLOR, alpha=0.4,
        interpolate=True
    )
    ax_delta.fill_between(
        dist_km, 0, delta,
        where=negative_mask,
        color=NEGATIVE_DELTA_COLOR, alpha=0.4,
        interpolate=True
    )
    ax_delta.plot(dist_km, delta, color=TEXT_COLOR, linewidth=1.5)
    
    ax_delta.axhline(y=0, color=AXIS_COLOR, linewidth=1)
    ax_delta.set_ylabel('Δ Time (s)', fontsize=11, fontweight='bold')
    ax_delta.set_xlabel('Distance (km)', fontsize=11, fontweight='bold')
    ax_delta.grid(True, alpha=0.3)
    
    # Add annotations for delta interpretation
    final_delta = delta[-1] if len(delta) > 0 else 0
    if final_delta > 0:
        delta_text = f'{comparison.lap2_label} is {abs(final_delta):.3f}s SLOWER'
        delta_color = POSITIVE_DELTA_COLOR
    else:
        delta_text = f'{comparison.lap2_label} is {abs(final_delta):.3f}s FASTER'
        delta_color = NEGATIVE_DELTA_COLOR
    
    ax_delta.text(
        0.98, 0.95, delta_text, transform=ax_delta.transAxes,
        fontsize=10, fontweight='bold', color=delta_color,
        ha='right', va='top',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#2a2a2a', edgecolor=delta_color)
    )
    
    # === Title ===
    if title is None:
        title = f"Telemetry Comparison: {comparison.lap1_label} vs {comparison.lap2_label}"
    
    # Add lap times to title if available
    subtitle_parts = []
    if comparison.lap1_time is not None:
        mins1 = int(comparison.lap1_time // 60)
        secs1 = comparison.lap1_time % 60
        subtitle_parts.append(f"{comparison.lap1_label}: {mins1}:{secs1:06.3f}")
    if comparison.lap2_time is not None:
        mins2 = int(comparison.lap2_time // 60)
        secs2 = comparison.lap2_time % 60
        subtitle_parts.append(f"{comparison.lap2_label}: {mins2}:{secs2:06.3f}")
    
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)
    if subtitle_parts:
        ax_speed.set_title(' | '.join(subtitle_parts), fontsize=10, alpha=0.8, pad=10)
    
    # Hide x-axis labels for upper panels
    plt.setp(ax_speed.get_xticklabels(), visible=False)
    plt.setp(ax_inputs.get_xticklabels(), visible=False)
    
    return fig, axes


def _add_drs_highlights(
    ax: Axes,
    comparison: TelemetryComparison,
    dist_km: np.ndarray,
) -> None:
    """
    Add semi-transparent DRS zone highlights to a chart panel.
    
    Args:
        ax: Matplotlib axes to add highlights to
        comparison: TelemetryComparison with DRS data
        dist_km: Distance array in kilometers
    """
    # Find DRS activation regions for lap1
    drs1_active = comparison.lap1_drs >= 10  # DRS is typically >= 10 when active
    
    if np.any(drs1_active):
        # Find continuous DRS regions
        drs_changes = np.diff(drs1_active.astype(int))
        drs_starts = np.where(drs_changes == 1)[0] + 1
        drs_ends = np.where(drs_changes == -1)[0] + 1
        
        # Handle edge cases
        if drs1_active[0]:
            drs_starts = np.concatenate([[0], drs_starts])
        if drs1_active[-1]:
            drs_ends = np.concatenate([drs_ends, [len(drs1_active)]])
        
        # Add vertical spans for DRS zones
        for start, end in zip(drs_starts, drs_ends):
            if start < len(dist_km) and end <= len(dist_km):
                ax.axvspan(
                    float(dist_km[start]), float(dist_km[min(end, len(dist_km)-1)]),
                    alpha=0.1, color='#00ff00', zorder=0
                )


def show_comparison_chart(
    comparison: TelemetryComparison,
    title: Optional[str] = None,
    figsize: Tuple[float, float] = (14, 10),
    save_path: Optional[str] = None,
    show_gear: bool = False,
    show_drs: bool = True,
) -> None:
    """
    Create and display (or save) a telemetry comparison chart.
    
    Args:
        comparison: TelemetryComparison object with aligned data
        title: Chart title (auto-generated if None)
        figsize: Figure size (width, height) in inches
        save_path: If provided, save figure to this path instead of showing
        show_gear: Whether to overlay gear numbers on speed panel
        show_drs: Whether to highlight DRS activation zones
    """
    fig, axes = create_comparison_chart(
        comparison, title, figsize, show_gear, show_drs
    )
    
    if save_path:
        fig.savefig(save_path, dpi=150, facecolor=BACKGROUND_COLOR, bbox_inches='tight')
        print(f"Chart saved to: {save_path}")
    else:
        plt.show()
    
    plt.close(fig)


def create_mini_comparison_chart(
    comparison: TelemetryComparison,
    figsize: Tuple[float, float] = (8, 4),
) -> Tuple[Figure, Axes]:
    """
    Create a simplified single-panel speed comparison chart.
    
    Useful for embedding in other interfaces or quick comparisons.
    
    Args:
        comparison: TelemetryComparison object with aligned data
        figsize: Figure size (width, height) in inches
        
    Returns:
        Tuple of (Figure, Axes)
    """
    setup_dark_style()
    
    fig, ax = plt.subplots(figsize=figsize)
    
    dist_km = comparison.distance / 1000.0
    
    ax.plot(
        dist_km, comparison.lap1_speed,
        color=comparison.lap1_color, linewidth=1.5,
        label=comparison.lap1_label
    )
    ax.plot(
        dist_km, comparison.lap2_speed,
        color=comparison.lap2_color, linewidth=1.5,
        label=comparison.lap2_label
    )
    
    ax.set_xlabel('Distance (km)')
    ax.set_ylabel('Speed (km/h)')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    
    final_delta = comparison.delta_time[-1] if len(comparison.delta_time) > 0 else 0
    delta_sign = '+' if final_delta > 0 else ''
    ax.set_title(f'Speed Comparison | Δ: {delta_sign}{final_delta:.3f}s')
    
    return fig, ax
