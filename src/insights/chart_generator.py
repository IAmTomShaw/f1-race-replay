import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
import pandas as pd
import numpy as np
from typing import Dict, List, Any
import fastf1.plotting

# Enable FastF1 plotting
fastf1.plotting.setup_mpl()


class RaceInsightCharts:
    """Generate various race insight charts and visualizations."""
    
    def __init__(self, session, driver_colors: Dict[str, str]):
        self.session = session
        self.driver_colors = driver_colors
        self.laps = session.laps
        
    def get_track_evolution(self) -> plt.Figure:
        """Analyze and visualize track evolution over the race."""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Get lap times for each driver
        for driver in self.session.drivers:
            driver_laps = self.laps.pick_driver(driver)
            if len(driver_laps) == 0:
                continue
                
            # Filter out pit laps and anomalies
            valid_laps = driver_laps[driver_laps['PitOutTime'].isna()]
            
            if len(valid_laps) > 0:
                lap_numbers = valid_laps['LapNumber']
                lap_times = valid_laps['LapTime'].dt.total_seconds()
                
                color = self.driver_colors.get(driver, '#808080')
                ax.plot(lap_numbers, lap_times, marker='o', markersize=3, 
                       label=driver, color=color, alpha=0.7)
        
        ax.set_xlabel('Lap Number', fontsize=12)
        ax.set_ylabel('Lap Time (seconds)', fontsize=12)
        ax.set_title('Track Evolution - Lap Times Throughout the Race', fontsize=14, fontweight='bold')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        
        return fig
    
    def get_tyre_strategy(self) -> plt.Figure:
        """Visualize tyre strategy comparison for all drivers."""
        fig, ax = plt.subplots(figsize=(12, 8))
        
        drivers = self.session.drivers
        compound_colors = {
            'SOFT': '#FF0000',
            'MEDIUM': '#FFF200',
            'HARD': '#FFFFFF',
            'INTERMEDIATE': '#00FF00',
            'WET': '#0000FF'
        }
        
        y_position = 0
        driver_positions = {}
        
        for driver in drivers:
            driver_laps = self.laps.pick_driver(driver)
            if len(driver_laps) == 0:
                continue
            
            driver_positions[driver] = y_position
            
            # Group consecutive laps with same compound
            current_compound = None
            stint_start = 0
            
            for idx, lap in driver_laps.iterrows():
                lap_num = lap['LapNumber']
                compound = lap['Compound']
                
                if compound != current_compound:
                    if current_compound is not None:
                        # Draw previous stint
                        color = compound_colors.get(current_compound, '#808080')
                        ax.barh(y_position, lap_num - stint_start, left=stint_start, 
                               height=0.8, color=color, edgecolor='black', linewidth=0.5)
                    
                    current_compound = compound
                    stint_start = lap_num
            
            # Draw final stint
            if current_compound is not None:
                color = compound_colors.get(current_compound, '#808080')
                final_lap = driver_laps['LapNumber'].max()
                ax.barh(y_position, final_lap - stint_start + 1, left=stint_start, 
                       height=0.8, color=color, edgecolor='black', linewidth=0.5)
            
            y_position += 1
        
        ax.set_yticks(list(driver_positions.values()))
        ax.set_yticklabels(list(driver_positions.keys()))
        ax.set_xlabel('Lap Number', fontsize=12)
        ax.set_ylabel('Driver', fontsize=12)
        ax.set_title('Tyre Strategy Comparison', fontsize=14, fontweight='bold')
        
        # Create legend
        legend_patches = [mpatches.Patch(color=color, label=compound) 
                         for compound, color in compound_colors.items()]
        ax.legend(handles=legend_patches, loc='upper right')
        ax.grid(True, axis='x', alpha=0.3)
        plt.tight_layout()
        
        return fig
    
    def get_pitstop_analysis(self) -> plt.Figure:
        """Analyze pit stop times and strategies."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Get pit stop data
        pit_data = []
        for driver in self.session.drivers:
            driver_laps = self.laps.pick_driver(driver)
            pit_laps = driver_laps[driver_laps['PitInTime'].notna()]
            
            for idx, lap in pit_laps.iterrows():
                if pd.notna(lap['PitOutTime']) and pd.notna(lap['PitInTime']):
                    pit_duration = (lap['PitOutTime'] - lap['PitInTime']).total_seconds()
                    pit_data.append({
                        'Driver': driver,
                        'Lap': lap['LapNumber'],
                        'Duration': pit_duration,
                        'Compound': lap['Compound']
                    })
        
        if pit_data:
            pit_df = pd.DataFrame(pit_data)
            
            # Chart 1: Pit stop durations
            for driver in pit_df['Driver'].unique():
                driver_pits = pit_df[pit_df['Driver'] == driver]
                color = self.driver_colors.get(driver, '#808080')
                ax1.scatter(driver_pits['Lap'], driver_pits['Duration'], 
                           label=driver, color=color, s=100, alpha=0.7)
            
            ax1.set_xlabel('Lap Number', fontsize=12)
            ax1.set_ylabel('Pit Stop Duration (seconds)', fontsize=12)
            ax1.set_title('Pit Stop Times Throughout the Race', fontsize=14, fontweight='bold')
            ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
            ax1.grid(True, alpha=0.3)
            
            # Chart 2: Number of pit stops per driver
            pit_counts = pit_df.groupby('Driver').size()
            colors = [self.driver_colors.get(driver, '#808080') for driver in pit_counts.index]
            ax2.bar(range(len(pit_counts)), pit_counts.values, color=colors)
            ax2.set_xticks(range(len(pit_counts)))
            ax2.set_xticklabels(pit_counts.index, rotation=45, ha='right')
            ax2.set_ylabel('Number of Pit Stops', fontsize=12)
            ax2.set_title('Total Pit Stops per Driver', fontsize=14, fontweight='bold')
            ax2.grid(True, axis='y', alpha=0.3)
        else:
            ax1.text(0.5, 0.5, 'No pit stop data available', 
                    ha='center', va='center', fontsize=14)
            ax2.text(0.5, 0.5, 'No pit stop data available', 
                    ha='center', va='center', fontsize=14)
        
        plt.tight_layout()
        return fig
    
    def get_driver_performance(self, drivers: List[str] = None) -> plt.Figure:
        """Analyze driver performance over time (lap times, positions)."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        if drivers is None:
            drivers = self.session.drivers[:5]  # Top 5 by default
        
        # Chart 1: Position over time
        for driver in drivers:
            driver_laps = self.laps.pick_driver(driver)
            if len(driver_laps) > 0:
                color = self.driver_colors.get(driver, '#808080')
                ax1.plot(driver_laps['LapNumber'], driver_laps['Position'], 
                        marker='o', label=driver, color=color, linewidth=2)
        
        ax1.set_xlabel('Lap Number', fontsize=12)
        ax1.set_ylabel('Position', fontsize=12)
        ax1.set_title('Position Changes Throughout the Race', fontsize=14, fontweight='bold')
        ax1.invert_yaxis()  # Position 1 at top
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Chart 2: Lap time delta to fastest
        fastest_lap_time = self.laps['LapTime'].min()
        
        for driver in drivers:
            driver_laps = self.laps.pick_driver(driver)
            valid_laps = driver_laps[driver_laps['LapTime'].notna()]
            
            if len(valid_laps) > 0:
                delta = (valid_laps['LapTime'] - fastest_lap_time).dt.total_seconds()
                color = self.driver_colors.get(driver, '#808080')
                ax2.plot(valid_laps['LapNumber'], delta, 
                        marker='o', label=driver, color=color, linewidth=2, alpha=0.7)
        
        ax2.set_xlabel('Lap Number', fontsize=12)
        ax2.set_ylabel('Delta to Fastest Lap (seconds)', fontsize=12)
        ax2.set_title('Lap Time Performance Relative to Fastest Lap', fontsize=14, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=0, color='red', linestyle='--', linewidth=1, alpha=0.5)
        
        plt.tight_layout()
        return fig
    
    def get_sector_comparison(self, drivers: List[str] = None) -> plt.Figure:
        """Compare sector times between drivers."""
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        if drivers is None:
            drivers = self.session.drivers[:5]
        
        sector_data = {1: [], 2: [], 3: []}
        
        for driver in drivers:
            driver_laps = self.laps.pick_driver(driver)
            fastest_lap = driver_laps.pick_fastest()
            
            if fastest_lap is not None and not fastest_lap.empty:
                for sector in [1, 2, 3]:
                    sector_col = f'Sector{sector}Time'
                    if sector_col in fastest_lap and pd.notna(fastest_lap[sector_col]):
                        sector_time = fastest_lap[sector_col].total_seconds()
                        sector_data[sector].append((driver, sector_time))
        
        for sector, ax in zip([1, 2, 3], axes):
            if sector_data[sector]:
                drivers_list = [d[0] for d in sector_data[sector]]
                times = [d[1] for d in sector_data[sector]]
                colors = [self.driver_colors.get(d, '#808080') for d in drivers_list]
                
                bars = ax.bar(range(len(drivers_list)), times, color=colors)
                ax.set_xticks(range(len(drivers_list)))
                ax.set_xticklabels(drivers_list, rotation=45, ha='right')
                ax.set_ylabel('Time (seconds)', fontsize=10)
                ax.set_title(f'Sector {sector} Times', fontsize=12, fontweight='bold')
                ax.grid(True, axis='y', alpha=0.3)
                
                # Highlight fastest
                min_time_idx = times.index(min(times))
                bars[min_time_idx].set_edgecolor('gold')
                bars[min_time_idx].set_linewidth(3)
        
        plt.suptitle('Sector Time Comparison (Fastest Laps)', fontsize=14, fontweight='bold')
        plt.tight_layout()
        return fig
    
    def get_gap_analysis(self, reference_driver: str = None) -> plt.Figure:
        """Analyze gaps between drivers throughout the race."""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        if reference_driver is None:
            # Use race winner as reference
            final_laps = self.laps[self.laps['LapNumber'] == self.laps['LapNumber'].max()]
            reference_driver = final_laps.loc[final_laps['Position'].idxmin(), 'Driver']
        
        ref_laps = self.laps.pick_driver(reference_driver)
        
        for driver in self.session.drivers:
            if driver == reference_driver:
                continue
                
            driver_laps = self.laps.pick_driver(driver)
            gaps = []
            lap_numbers = []
            
            for lap_num in driver_laps['LapNumber']:
                ref_lap = ref_laps[ref_laps['LapNumber'] == lap_num]
                drv_lap = driver_laps[driver_laps['LapNumber'] == lap_num]
                
                if not ref_lap.empty and not drv_lap.empty:
                    ref_time = ref_lap.iloc[0]['Time']
                    drv_time = drv_lap.iloc[0]['Time']
                    
                    if pd.notna(ref_time) and pd.notna(drv_time):
                        gap = (drv_time - ref_time).total_seconds()
                        gaps.append(gap)
                        lap_numbers.append(lap_num)
            
            if gaps:
                color = self.driver_colors.get(driver, '#808080')
                ax.plot(lap_numbers, gaps, label=driver, color=color, linewidth=2, alpha=0.7)
        
        ax.set_xlabel('Lap Number', fontsize=12)
        ax.set_ylabel(f'Gap to {reference_driver} (seconds)', fontsize=12)
        ax.set_title(f'Gap Analysis - All Drivers vs {reference_driver}', fontsize=14, fontweight='bold')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=2)
        plt.tight_layout()
        
        return fig
