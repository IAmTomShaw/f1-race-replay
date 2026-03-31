import arcade
import numpy as np
from typing import List
from .progress_bar import RaceProgressBarComponent

# Extract race events from frame data for the progress bar.
def extract_race_events(frames: List[dict], track_statuses: List[dict], total_laps: int) -> List[dict]:
    """
    Extract race events from frame data for the progress bar.
    identifies: DNF events, Leader changes, Flag events
    """
    events = []
    if not frames:
        return events
        
    n_frames = len(frames)
    prev_drivers = set()
    sample_rate = 25
    
    for i in range(0, n_frames, sample_rate):
        frame = frames[i]
        drivers_data = frame.get("drivers", {})
        current_drivers = set(drivers_data.keys())
        
        if prev_drivers:
            dnf_drivers = prev_drivers - current_drivers
            for driver_code in dnf_drivers:
                prev_frame = frames[max(0, i - sample_rate)]
                driver_info = prev_frame.get("drivers", {}).get(driver_code, {})
                lap = driver_info.get("lap", "?")
                
                events.append({
                    "type": RaceProgressBarComponent.EVENT_DNF,
                    "frame": i,
                    "label": driver_code,
                    "lap": lap,
                })
        
        prev_drivers = current_drivers
    
    for status in track_statuses:
        status_code = str(status.get("status", ""))
        start_time = status.get("start_time", 0)
        end_time = status.get("end_time")
        
        fps = 25
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time else start_frame + 250
        
        if end_frame <= 0:
            continue
        
        if n_frames > 0:
            end_frame = min(end_frame, n_frames)
        
        event_type = None
        if status_code == "2":  # Yellow flag
            event_type = RaceProgressBarComponent.EVENT_YELLOW_FLAG
        elif status_code == "4":  # Safety Car
            event_type = RaceProgressBarComponent.EVENT_SAFETY_CAR
        elif status_code == "5":  # Red flag
            event_type = RaceProgressBarComponent.EVENT_RED_FLAG
        elif status_code in ("6", "7"):  # VSC
            event_type = RaceProgressBarComponent.EVENT_VSC
            
        if event_type:
            events.append({
                "type": event_type,
                "frame": start_frame,
                "end_frame": end_frame,
                "label": "",
                "lap": None,
            })
    return events

# Build track geometry from example lap telemetry
def build_track_from_example_lap(example_lap, track_width=200):
    drs_zones = plotDRSzones(example_lap)
    plot_x_ref = example_lap["X"]
    plot_y_ref = example_lap["Y"]

    dx = np.gradient(plot_x_ref)
    dy = np.gradient(plot_y_ref)

    norm = np.sqrt(dx**2 + dy**2)
    norm[norm == 0] = 1.0
    dx /= norm
    dy /= norm

    nx = -dy
    ny = dx

    x_outer = plot_x_ref + nx * (track_width / 2)
    y_outer = plot_y_ref + ny * (track_width / 2)
    x_inner = plot_x_ref - nx * (track_width / 2)
    y_inner = plot_y_ref - ny * (track_width / 2)

    x_min = min(plot_x_ref.min(), x_inner.min(), x_outer.min())
    x_max = max(plot_x_ref.max(), x_inner.max(), x_outer.max())
    y_min = min(plot_y_ref.min(), y_inner.min(), y_outer.min())
    y_max = max(plot_y_ref.max(), y_inner.max(), y_outer.max())

    return (plot_x_ref, plot_y_ref, x_inner, y_inner, x_outer, y_outer,
            x_min, x_max, y_min, y_max, drs_zones)

# Plot DRS Zones
def plotDRSzones(example_lap):
   x_val = example_lap["X"]
   y_val = example_lap["Y"]
   drs_zones = []
   drs_start = None

   for i, val in enumerate(example_lap["DRS"]):
       if val in [10, 12, 14]:
           if drs_start is None:
               drs_start = i
       else:
           if drs_start is not None:
               drs_end = i - 1
               zone = {
                   "start": {"x": x_val.iloc[drs_start], "y": y_val.iloc[drs_start], "index": drs_start},
                   "end": {"x": x_val.iloc[drs_end], "y": y_val.iloc[drs_end], "index": drs_end}
               }
               drs_zones.append(zone)
               drs_start = None
   
   if drs_start is not None:
       drs_end = len(example_lap["DRS"]) - 1
       zone = {
           "start": {"x": x_val.iloc[drs_start], "y": y_val.iloc[drs_start], "index": drs_start},
           "end": {"x": x_val.iloc[drs_end], "y": y_val.iloc[drs_end], "index": drs_end}
       }
       drs_zones.append(zone)
   return drs_zones

# Draw checkered finish line
def draw_finish_line(self, session_type = 'R'):
    if(session_type not in ['R', 'Q']):
        return

    start_inner = None
    start_outer = None

    if(session_type == 'Q' and len(self.inner_pts) > 0 and len(self.outer_pts) > 0):
        start_inner = self.inner_pts[0]
        start_outer = self.outer_pts[0]
    elif(session_type == 'R' and len(self.screen_inner_points) > 0 and len(self.screen_outer_points) > 0):
        start_inner = self.screen_inner_points[0]
        start_outer = self.screen_outer_points[0]
    else:
        return
    
    if start_inner and start_outer:
        num_squares = 20
        extension = 20
        dx = start_outer[0] - start_inner[0]
        dy = start_outer[1] - start_inner[1]
        length = np.sqrt(dx**2 + dy**2)
            
        if length > 0:
            dx_norm = dx / length
            dy_norm = dy / length
            extended_inner = (start_inner[0] - extension * dx_norm, 
                             start_inner[1] - extension * dy_norm)
            extended_outer = (start_outer[0] + extension * dx_norm, 
                             start_outer[1] + extension * dy_norm)
            
            for i in range(num_squares):
                t1 = i / num_squares 
                t2 = (i + 1) / num_squares 
                x1 = extended_inner[0] + t1 * (extended_outer[0] - extended_inner[0])
                y1 = extended_inner[1] + t1 * (extended_outer[1] - extended_inner[1])
                x2 = extended_inner[0] + t2 * (extended_outer[0] - extended_inner[0])
                y2 = extended_inner[1] + t2 * (extended_outer[1] - extended_inner[1])
                color = arcade.color.WHITE if i % 2 == 0 else arcade.color.BLACK
                arcade.draw_line(x1, y1, x2, y2, color, 6)
