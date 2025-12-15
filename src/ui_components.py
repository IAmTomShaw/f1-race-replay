import arcade
from typing import List, Tuple, Optional
from typing import Sequence, Optional, Tuple
from src.lib.time import format_time
import numpy as np
import os
import arcade.gui
import threading
from PIL import Image, ImageDraw, ImageFont
from src.wiki_utils import fetch_circuit_image

def _format_wind_direction(degrees: Optional[float]) -> str:
  if degrees is None:
      return "N/A"
  deg_norm = degrees % 360
  dirs = [
      "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ]
  idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
  return dirs[idx]

class BaseComponent:
    def on_resize(self, window): pass
    def draw(self, window): pass
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int): return False

class LegendComponent(BaseComponent):
    def __init__(self, x: int = 20, y: int = 150):
        self.x = x
        self.y = y
        self.lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[R]       Restart",
        ]
    def draw(self, window):
        for i, line in enumerate(self.lines):
            arcade.Text(
                line,
                self.x,
                self.y - (i * 25),
                arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                14,
                bold=(i == 0)
            ).draw()

class WeatherComponent(BaseComponent):
    def __init__(self, left=20, width=280, height=130, top_offset=170):
        self.left = left
        self.width = width
        self.height = height
        self.top_offset = top_offset
        self.info = None
        self._weather_icon_textures = {}
        # Load weather icons from images/weather folder (all files)
        weather_folder = os.path.join("images", "weather")
        if os.path.exists(weather_folder):
            for filename in os.listdir(weather_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(weather_folder, filename)
                    self._weather_icon_textures[texture_name] = arcade.load_texture(texture_path)

    def set_info(self, info: Optional[dict]):
        self.info = info
    def draw(self, window):
        panel_top = window.height - self.top_offset
        if not self.info and not getattr(window, "has_weather", False):
            return
        arcade.Text("Weather", self.left + 12, panel_top - 10, arcade.color.WHITE, 18, bold=True, anchor_y="top").draw()
        def _fmt(val, suffix="", precision=1):
            return f"{val:.{precision}f}{suffix}" if val is not None else "N/A"
        info = self.info or {}
        # Map each weather line to its corresponding icon
        weather_lines = [
            ("Track", f"{_fmt(info.get('track_temp'), '°C')}", "thermometer"),
            ("Air", f"{_fmt(info.get('air_temp'), '°C')}", "thermometer"),
            ("Humidity", f"{_fmt(info.get('humidity'), '%', precision=0)}", "drop"),
            ("Wind", f"{_fmt(info.get('wind_speed'), ' km/h')} {_format_wind_direction(info.get('wind_direction'))}", "wind"),
            ("Rain", f"{info.get('rain_state','N/A')}", "rain"),
        ]
        
        start_y = panel_top - 36
        for idx, (label, value, icon_key) in enumerate(weather_lines):
            line_y = start_y - idx * 22
            # Draw weather icon
            weather_texture = self._weather_icon_textures.get(icon_key)
            if weather_texture:
                weather_icon_x = self.left + 24
                weather_icon_y = line_y - 15
                icon_size = 16
                rect = arcade.XYWH(weather_icon_x, weather_icon_y, icon_size, icon_size)
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=weather_texture,
                    angle=0,
                    alpha=255
                )
            
            # Draw text
            line_text = f"{label}: {value}"
            arcade.Text(line_text, self.left + 38, line_y, arcade.color.LIGHT_GRAY, 14, anchor_y="top").draw()

class LeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of tuples (code, color, pos, progress_m)
        self.rects = []    # clickable rects per entry
        self.selected = None
        self.row_height = 25
        self._tyre_textures = {}
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

    def set_entries(self, entries: List[Tuple[str, Tuple[int,int,int], dict, float]]):
        # entries sorted as expected
        self.entries = entries
    def draw(self, window):
        leaderboard_y = window.height - 40
        arcade.Text("Leaderboard", self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
        self.rects = []
        for i, (code, color, pos, progress_m) in enumerate(self.entries):
            current_pos = i + 1
            top_y = leaderboard_y - 30 - ((current_pos - 1) * self.row_height)
            bottom_y = top_y - self.row_height
            left_x = self.x
            right_x = self.x + self.width
            self.rects.append((code, left_x, bottom_y, right_x, top_y))
            if code == self.selected:
                rect = arcade.XYWH((left_x + right_x)/2, (top_y + bottom_y)/2, right_x - left_x, top_y - bottom_y)
                arcade.draw_rect_filled(rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                text_color = color
            text = f"{current_pos}. {code}" if pos.get("rel_dist",0) != 1 else f"{current_pos}. {code}   OUT"
            arcade.Text(text, left_x, top_y, text_color, 16, anchor_x="left", anchor_y="top").draw()

             # Tyre Icons
            tyre_texture = self._tyre_textures.get(str(pos.get("tyre", "?")).upper())
            if tyre_texture:
                # position tyre icon inside the leaderboard area so it doesn't collide with track
                tyre_icon_x = left_x + self.width - 10
                tyre_icon_y = top_y - 12
                icon_size = 16

                rect = arcade.XYWH(tyre_icon_x, tyre_icon_y, icon_size, icon_size)

                # Draw the textured rect
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=tyre_texture,
                    angle=0,
                    alpha=255
                )


    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        for code, left, bottom, right, top in self.rects:
            if left <= x <= right and bottom <= y <= top:
                if self.selected == code:
                    self.selected = None
                else:
                    self.selected = code
                # propagate selection to window for compatibility
                window.selected_driver = self.selected
                return True
        return False

class LapTimeLeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of dicts: {'pos', 'code', 'color', 'time'}
        self.rects = []    # clickable rects per entry
        self.selected = None
        self.row_height = 25

    def set_entries(self, entries: List[dict]):
        """Accept a list of dicts with keys: pos, code, color, time"""
        self.entries = entries or []

    def draw(self, window):
        leaderboard_y = window.height - 40
        arcade.Text("Lap Times", self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
        self.rects = []
        for i, entry in enumerate(self.entries):
            pos = entry.get('pos', i + 1)
            code = entry.get('code', '')
            color = entry.get('color', arcade.color.WHITE)
            time_str = entry.get('time', '')
            current_pos = i + 1
            top_y = leaderboard_y - 30 - ((current_pos - 1) * self.row_height)
            bottom_y = top_y - self.row_height
            left_x = self.x
            right_x = self.x + self.width
            # store clickable rect (code, left, bottom, right, top)
            self.rects.append((code, left_x, bottom_y, right_x, top_y))

            # selection highlight
            if code == self.selected:
                rect = arcade.XYWH((left_x + right_x) / 2, (top_y + bottom_y) / 2, right_x - left_x, top_y - bottom_y)
                arcade.draw_rect_filled(rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                # accept tuple rgb or fallback to white
                text_color = tuple(color) if isinstance(color, (list, tuple)) else arcade.color.WHITE

            # Draw code on left, time right-aligned
            arcade.Text(f"{pos}. {code}", left_x + 8, top_y, text_color, 16, anchor_x="left", anchor_y="top").draw()
            arcade.Text(time_str, right_x - 8, top_y, text_color, 14, anchor_x="right", anchor_y="top").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        for code, left, bottom, right, top in self.rects:
            if left <= x <= right and bottom <= y <= top:
                if self.selected == code:
                    self.selected = None
                else:
                    self.selected = code
                # propagate selection to window
                window.selected_driver = self.selected
                return True
        return False

class QualifyingSegmentSelectorComponent(BaseComponent):
    def __init__(self, width=400, height=300):
        self.width = width
        self.height = height
        self.driver_result = None
        self.selected_segment = None
        
    def draw(self, window):
        if not getattr(window, "selected_driver", None):
            return
        
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        # Calculate modal position (centered)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Draw modal background
        modal_rect = arcade.XYWH(center_x, center_y, self.width, self.height)
        arcade.draw_rect_filled(modal_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(modal_rect, arcade.color.WHITE, 2)
        
        # Draw title
        title = f"Qualifying Sessions - {driver_result.get('code','')}"
        arcade.Text(title, left + 20, top - 30, arcade.color.WHITE, 18, 
               bold=True, anchor_x="left", anchor_y="center").draw()
        
        # Draw segments
        segment_height = 50
        start_y = top - 80

        segments = []

        if driver_result.get('Q1') is not None:
            segments.append({
                'time': driver_result['Q1'],
                'segment': 1
            })
        if driver_result.get('Q2') is not None:
            segments.append({
                'time': driver_result['Q2'],
                'segment': 2
            })
        if driver_result.get('Q3') is not None:
            segments.append({
                'time': driver_result['Q3'],
                'segment': 3
            })
        
        for i, data in enumerate(segments):
            segment = f"Q{data['segment']}"
            segment_top = start_y - (i * (segment_height + 10))
            segment_bottom = segment_top - segment_height
            
            # Highlight if selected
            segment_rect = arcade.XYWH(center_x, segment_top - segment_height//2, 
                                     self.width - 40, segment_height)
            
            if segment == self.selected_segment:
                arcade.draw_rect_filled(segment_rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                arcade.draw_rect_filled(segment_rect, (60, 60, 60))
                text_color = arcade.color.WHITE
                
            arcade.draw_rect_outline(segment_rect, arcade.color.WHITE, 1)
            
            # Draw segment info
            segment_text = f"{segment.upper()}"
            time_text = format_time(float(data.get('time', 'No Time')))
            
            arcade.Text(segment_text, left + 30, segment_top - 20, 
                       text_color, 16, bold=True, anchor_x="left", anchor_y="center").draw()
            arcade.Text(time_text, right - 30, segment_top - 20, 
                       text_color, 14, anchor_x="right", anchor_y="center").draw()
        
        # Draw close button
        close_btn_rect = arcade.XYWH(right - 30, top - 30, 20, 20)
        arcade.draw_rect_filled(close_btn_rect, arcade.color.RED)
        arcade.Text("×", right - 30, top - 30, arcade.color.WHITE, 16, 
               bold=True, anchor_x="center", anchor_y="center").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):        
        if not getattr(window, "selected_driver", None):
            return False
        
        # Calculate modal position (same as in draw)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Check close button (match the rect from draw method)
        close_btn_left = right - 30 - 10  # center - half width
        close_btn_right = right - 30 + 10  # center + half width
        close_btn_bottom = top - 30 - 10  # center - half height
        close_btn_top = top - 30 + 10     # center + half height
        
        if close_btn_left <= x <= close_btn_right and close_btn_bottom <= y <= close_btn_top:
            window.selected_driver = None
            # Also clear leaderboard selection state so UI highlight is removed
            if hasattr(window, "leaderboard") and getattr(window.leaderboard, "selected", None):
                window.leaderboard.selected = None
            self.selected_segment = None
            return True
        
        # Check segment clicks
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        
        if driver_result:
            segments = []
            if driver_result.get('Q1') is not None:
                segments.append({'time': driver_result['Q1'], 'segment': 1})
            if driver_result.get('Q2') is not None:
                segments.append({'time': driver_result['Q2'], 'segment': 2})
            if driver_result.get('Q3') is not None:
                segments.append({'time': driver_result['Q3'], 'segment': 3})
            
            segment_height = 50
            start_y = top - 80
            
            for i, data in enumerate(segments):
                segment_top = start_y - (i * (segment_height + 10))
                segment_bottom = segment_top - segment_height
                segment_left = left + 20
                segment_right = right - 20
            
                # If click falls inside this segment rect, toggle selection and start telemetry load
                if segment_left <= x <= segment_right and segment_bottom <= y <= segment_top:
                    segment = f"Q{data['segment']}"
                    # call window API to load telemetry and hide modal/selection
                    try:
                        # start loading telemetry on the main window
                        if hasattr(window, "load_driver_telemetry"):
                            window.load_driver_telemetry(code, segment)
                        # hide selector/modal and clear leaderboard highlight
                        window.selected_driver = None
                        if hasattr(window, "leaderboard"):
                            window.leaderboard.selected = None
                    except Exception as e:
                        print("Error starting telemetry load:", e)

                    return True
        
        return True  # Consume all clicks when visible


class DriverInfoComponent(BaseComponent):
    def __init__(self, left=20, width=300, min_top=220):
        self.left = left
        self.width = width
        self.min_top = min_top
    def draw(self, window):
        if not getattr(window, "selected_driver", None):
            return
        code = window.selected_driver
        frame = window.frames[min(int(window.frame_index), window.n_frames-1)]
        driver_pos = frame["drivers"].get(code, {})
        # layout
        info_x = self.left
        default_info_y = window.height / 2 + 100
        box_width = self.width
        box_height = 150
        weather_bottom = getattr(window, "weather_bottom", None)
        if weather_bottom is not None:
            target_top = weather_bottom - 20
            info_y = min(default_info_y, target_top - box_height / 2)
        else:
            info_y = default_info_y
        info_y = max(info_y, self.min_top + box_height / 2)
        # Draw name band + stats
        bg_rect = arcade.XYWH(info_x + box_width / 2, info_y - box_height / 2, box_width, box_height)
        arcade.draw_rect_outline(bg_rect, self._get_driver_color(window, code))
        name_rect = arcade.XYWH(info_x + box_width / 2, info_y + 20, box_width, 40)
        arcade.draw_rect_filled(name_rect, self._get_driver_color(window, code))
        arcade.Text(f"Driver: {code}", info_x + 10, info_y + 20, arcade.color.BLACK, 16, anchor_x="left", anchor_y="center").draw()
        # stats
        speed_text = f"Speed: {driver_pos.get('speed',0):.1f} km/h"
        gear_text = f"Gear: {driver_pos.get('gear',0)}"

        drs_status = "off"
        drs_value = driver_pos.get('drs', 0)
        if drs_value in [0, 1]:
            drs_status = "Off"
        elif drs_value == 8:
            drs_status = "Eligible"
        elif drs_value in [10, 12, 14]:
            drs_status = "On"
        else:
            drs_status = "Unknown"
        
        drs_text = f"DRS: {drs_status}"

        lines = [speed_text, gear_text, drs_text, f"Current Lap: {driver_pos.get('lap',1)}"]
        for i, ln in enumerate(lines):
            arcade.Text(ln, info_x + 10, info_y - 20 - (i * 25), arcade.color.WHITE, 14, anchor_x="left", anchor_y="center").draw()
    def _get_driver_color(self, window, code):
        return window.driver_colors.get(code, arcade.color.GRAY)
    
# Build track geometry from example lap telemetry

def build_track_from_example_lap(example_lap, track_width=200):

    plot_x_ref = example_lap["X"]
    plot_y_ref = example_lap["Y"]

    # compute tangents
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

    # world bounds
    x_min = min(plot_x_ref.min(), x_inner.min(), x_outer.min())
    x_max = max(plot_x_ref.max(), x_inner.max(), x_outer.max())
    y_min = min(plot_y_ref.min(), y_inner.min(), y_outer.min())
    y_max = max(plot_y_ref.max(), y_inner.max(), y_outer.max())

    return (plot_x_ref, plot_y_ref, x_inner, y_inner, x_outer, y_outer,
            x_min, x_max, y_min, y_max)


class CircuitGridButton(arcade.gui.UITextureButton):

    def __init__(self, round_num, event_name, year, country, circuit_name, width=250, height=140):
        w, h = int(width), int(height)

        clean_event_name = event_name.replace('Grand Prix', 'GP')
        display_text = f"R{round_num}\n{clean_event_name}\n{circuit_name} Circuit"

        # Normal state: Dark Gray
        normal_pil = Image.new("RGBA", (w, h), (40, 40, 40, 255))
        # Hover state: Brighter Gray (100) for better visibility
        hover_pil = Image.new("RGBA", (w, h), (100, 100, 100, 255))

        self._draw_text_on_image(normal_pil, display_text)

        self.normal_tex = arcade.Texture(name=f"btn_norm_{round_num}", image=normal_pil)
        self.hover_base_tex = arcade.Texture(name=f"btn_hover_base_{round_num}", image=hover_pil)

        super().__init__(
            texture=self.normal_tex,
            texture_hovered=self.hover_base_tex,
            texture_pressed=self.hover_base_tex,
            text="",
            width=w, height=h, size_hint=(None, None)
        )

        self.round_num = round_num;
        self.event_name = event_name;
        self.year = year;
        self.country = country
        self.image_path = None;
        self.texture_loaded = False
        self._start_image_download()

    def _draw_text_on_image(self, image, text):
        draw = ImageDraw.Draw(image)
        w, h = image.size

        # Dynamic font size based on button width
        font_size = max(14, int(w / 16))

        # Try to load a standard font, fallback to default if not found
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()

        lines = text.split('\n')
        line_spacing = 6  # Adjusted line spacing for better readability

        # Calculate heights for vertical centering
        line_heights = []
        total_text_height = 0

        for line in lines:
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), line, font=font)
                lh = bbox[3] - bbox[1]
            else:
                lh = draw.textsize(line, font=font)[1]
            lh = max(lh, font_size)
            line_heights.append(lh)
            total_text_height += lh

        total_text_height += (len(lines) - 1) * line_spacing

        # Start drawing
        current_y = (h - total_text_height) / 2

        for i, line in enumerate(lines):
            # Calculate width for horizontal centering
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), line, font=font)
                lw = bbox[2] - bbox[0]
            else:
                lw = draw.textsize(line, font=font)[0]

            current_x = (w - lw) / 2

            # Draw text (White color)
            draw.text((current_x, current_y), line, font=font, fill=(255, 255, 255))
            current_y += line_heights[i] + line_spacing

    def _start_image_download(self):
        threading.Thread(target=fetch_circuit_image,
                         args=(self.year, self.event_name, lambda path: setattr(self, 'image_path', path)),
                         daemon=True).start()

    def on_update(self, dt):
        if self.image_path and not self.texture_loaded:
            try:
                # 1. Load Image
                pil_image = Image.open(self.image_path).convert("RGBA")

                # 2. Crop transparent margins
                bbox = pil_image.getbbox()
                if bbox: pil_image = pil_image.crop(bbox)

                # 3. Prepare Canvas
                btn_w, btn_h = int(self.width), int(self.height)

                # Copy the clean hover base (no text)
                base_img = self.hover_base_tex.image.copy().convert("RGBA")

                # Resize base if dimensions mismatch (handling dynamic resizing)
                if base_img.size != (btn_w, btn_h):
                    base_img = base_img.resize((btn_w, btn_h), Image.Resampling.LANCZOS)

                # 4. Aspect Ratio Preserving Resize (Contain)
                img_w, img_h = pil_image.size

                ratio_w = btn_w / img_w
                ratio_h = btn_h / img_h

                # Use the smaller ratio to ensure the image fits entirely
                scale = min(ratio_w, ratio_h)
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)

                final_track_img = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # 5. Center Paste
                dest_x = (btn_w - new_w) // 2
                dest_y = (btn_h - new_h) // 2

                base_img.paste(final_track_img, (dest_x, dest_y), final_track_img)

                # 6. Apply Texture
                composite_texture = arcade.Texture(name=f"{self.event_name}_composite", image=base_img)
                self.texture_hovered = composite_texture
                self.texture_pressed = composite_texture
                self.texture_loaded = True
                self.trigger_render()
            except Exception as e:
                print(f"Texture Load Error: {e}")
                self.texture_loaded = True
        super().on_update(dt)