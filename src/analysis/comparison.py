import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from src.lib.tyres import get_tyre_compound_int

# Setup FastF1 plotting styling (removed deprecated argument)
fastf1.plotting.setup_mpl()

class TelemetryComparator:
    def __init__(self, session, driver_a_code, driver_b_code, lap_number=None):
        self.session = session
        self.d1_code = driver_a_code
        self.d2_code = driver_b_code
        self.lap_number = lap_number
        self.telemetry_data = {}
        self.delta_data = None
        self.laps = {}
        
    def process(self):
        """Fetch and align telemetry for both drivers."""
        print(f"Processing comparison: {self.d1_code} vs {self.d2_code}")
        
        # 1. Select Laps
        d1_laps = self.session.laps.pick_drivers(self.d1_code)
        d2_laps = self.session.laps.pick_drivers(self.d2_code)

        if d1_laps.empty:
            raise ValueError(f"Driver {self.d1_code} not found in this session.")
        if d2_laps.empty:
            raise ValueError(f"Driver {self.d2_code} not found in this session.")

        if self.lap_number:
            # Try to select the specific lap
            lap_a = d1_laps[d1_laps['LapNumber'] == self.lap_number]
            lap_b = d2_laps[d2_laps['LapNumber'] == self.lap_number]
            
            if lap_a.empty or lap_b.empty:
                raise ValueError(f"Lap {self.lap_number} not available for one or both drivers.")
            
            lap_a = lap_a.iloc[0]
            lap_b = lap_b.iloc[0]
        else:
            # Default to fastest lap
            print("No lap specified, selecting fastest laps for both drivers.")
            lap_a = d1_laps.pick_fastest()
            lap_b = d2_laps.pick_fastest()

        self.laps = {self.d1_code: lap_a, self.d2_code: lap_b}
        
        # 2. Get Telemetry and add 'Distance' for alignment
        # We assume standard car data (Speed, RPM, Gear, etc.)
        try:
            tel_a = lap_a.get_car_data().add_distance()
            tel_b = lap_b.get_car_data().add_distance()
        except Exception as e:
            raise ValueError(f"Could not retrieve telemetry: {e}")

        # 3. Create a common distance vector for interpolation
        # Use the shorter distance to avoid extrapolation errors at the finish line
        max_dist = min(tel_a['Distance'].max(), tel_b['Distance'].max())
        common_dist = np.linspace(0, max_dist, num=int(max_dist)) # 1 meter resolution

        # 4. Interpolate Data onto Common Distance
        aligned_data = {}
        
        # Helper to safely get color
        def get_color(code):
            try:
                return fastf1.plotting.get_driver_color(code, self.session)
            except:
                return "gray"

        for code, tel, color in [(self.d1_code, tel_a, get_color(self.d1_code)), 
                                 (self.d2_code, tel_b, get_color(self.d2_code))]:
            
            # Interpolate strictly numeric columns
            # We map the telemetry distance to our common distance
            interp_speed = np.interp(common_dist, tel['Distance'], tel['Speed'])
            interp_time = np.interp(common_dist, tel['Distance'], tel['Time'].dt.total_seconds())
            interp_throttle = np.interp(common_dist, tel['Distance'], tel['Throttle'])
            interp_brake = np.interp(common_dist, tel['Distance'], tel['Brake'])
            interp_gear = np.interp(common_dist, tel['Distance'], tel['nGear'])
            
            aligned_data[code] = {
                'dist': common_dist,
                'time': interp_time,
                'speed': interp_speed,
                'throttle': interp_throttle,
                'brake': interp_brake,
                'gear': interp_gear,
                'color': color
            }

        self.telemetry_data = aligned_data
        
        # 5. Compute Time Delta
        # Positive delta = Driver B is slower (behind) Driver A (if they started at the same time)
        # More accurately: At distance X, how much later did Driver B arrive than Driver A?
        self.delta_data = aligned_data[self.d2_code]['time'] - aligned_data[self.d1_code]['time']
        
        return self._generate_statistics()

    def _generate_statistics(self):
        """Generate summary statistics for the comparison."""
        d1 = self.telemetry_data[self.d1_code]
        d2 = self.telemetry_data[self.d2_code]
        
        # Convert Timedelta to float seconds for subtraction if needed, 
        # but LapTime is usually a Timedelta.
        t1 = self.laps[self.d1_code]['LapTime']
        t2 = self.laps[self.d2_code]['LapTime']
        
        diff = t1 - t2
        diff_seconds = diff.total_seconds()

        stats = {
            "top_speed_diff": np.max(d1['speed']) - np.max(d2['speed']),
            "avg_throttle_a": np.mean(d1['throttle']),
            "avg_throttle_b": np.mean(d2['throttle']),
            "lap_time_diff": diff_seconds
        }
        return stats

    def plot_comparison(self):
        """Create and show the Matplotlib visualization."""
        if not self.telemetry_data:
            self.process()

        # Create 4 subplots sharing the X axis (Distance)
        fig, ax = plt.subplots(4, 1, figsize=(14, 10), sharex=True, 
                               gridspec_kw={'height_ratios': [3, 1, 1, 1.5]})
        
        d1 = self.telemetry_data[self.d1_code]
        d2 = self.telemetry_data[self.d2_code]
        dist = d1['dist']
        
        c1 = d1['color']
        c2 = d2['color']
        
        # Format Lap Times for Legend
        t1_str = str(self.laps[self.d1_code]['LapTime']).split('days')[-1].strip()
        t2_str = str(self.laps[self.d2_code]['LapTime']).split('days')[-1].strip()

        # --- 1. Speed Trace ---
        ax[0].plot(dist, d1['speed'], color=c1, label=f"{self.d1_code} ({t1_str})")
        ax[0].plot(dist, d2['speed'], color=c2, label=f"{self.d2_code} ({t2_str})")
        ax[0].set_ylabel("Speed (km/h)")
        ax[0].legend(loc="lower left")
        ax[0].grid(True, alpha=0.3)
        ax[0].set_title(f"Telemetry Comparison: {self.d1_code} vs {self.d2_code}")

        # --- 2. Throttle ---
        ax[1].plot(dist, d1['throttle'], color=c1, label=self.d1_code)
        ax[1].plot(dist, d2['throttle'], color=c2, label=self.d2_code, linestyle="--")
        ax[1].set_ylabel("Throttle %")
        ax[1].set_ylim(-5, 105)
        ax[1].grid(True, alpha=0.3)

        # --- 3. Brake ---
        ax[2].plot(dist, d1['brake'], color=c1, label=self.d1_code)
        ax[2].plot(dist, d2['brake'], color=c2, label=self.d2_code, linestyle="--")
        ax[2].set_ylabel("Brake")
        ax[2].grid(True, alpha=0.3)

        # --- 4. Time Delta ---
        # Draw a zero line
        ax[3].axhline(0, color='white', linestyle='--', linewidth=1)
        
        # Plot delta line
        ax[3].plot(dist, self.delta_data, color='white', linewidth=1.5)
        
        # Fill logic: 
        # If Delta > 0, Driver B arrived LATER -> Driver A is Ahead (Color A)
        # If Delta < 0, Driver B arrived EARLIER -> Driver B is Ahead (Color B)
        ax[3].fill_between(dist, 0, self.delta_data, where=self.delta_data>0, 
                           facecolor=c1, alpha=0.4, label=f"{self.d1_code} Ahead")
        ax[3].fill_between(dist, 0, self.delta_data, where=self.delta_data<0, 
                           facecolor=c2, alpha=0.4, label=f"{self.d2_code} Ahead")
        
        ax[3].set_ylabel(f"Gap (s)\n(+ means {self.d2_code} behind)")
        ax[3].set_xlabel("Distance (m)")
        ax[3].legend(loc="upper left")
        ax[3].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()