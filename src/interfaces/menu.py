import arcade
import arcade.gui
import fastf1
from datetime import datetime
import threading

# Define a custom event for when the menu finishes
START_SESSION_EVENT = "START_SESSION"

class MainMenuWindow(arcade.Window):
    def __init__(self):
        super().__init__(800, 600, "F1 Race Replay - Menu", resizable=True)
        
        self.manager = arcade.gui.UIManager()
        self.manager.enable()
        
        arcade.set_background_color(arcade.color.AMAZON)

        self.v_box = arcade.gui.UIBoxLayout(space_between=20)
        
        # Title
        title_label = arcade.gui.UILabel(text="F1 Race Replay", font_size=30, bold=True, text_color=arcade.color.WHITE)
        self.v_box.add(title_label)
        
        # --- Year Selection ---
        self.year_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)
        self.year_label = arcade.gui.UILabel(text="Year:", width=100, align="right")
        self.year_box.add(self.year_label)
        
        current_year = datetime.now().year
        self.available_years = [str(y) for y in range(current_year, 2017, -1)]
        self.selected_year = str(current_year)
        
        # Custom button to act as dropdown trigger (simplification)
        # Using UIInputText or similar might be complex, so we'll use a simple cycle button for now
        # or just a text input. Let's try to make a cleaner UI with buttons or a list.
        # Actually, let's use a horizontal box with Prev/Next buttons for Year.
        
        self.year_selector = self._create_selector(self.selected_year, self._on_prev_year, self._on_next_year)
        self.year_box.add(self.year_selector)
        self.v_box.add(self.year_box)
        
        # --- Round Selection ---
        self.round_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)
        self.round_label = arcade.gui.UILabel(text="Round:", width=100, align="right")
        self.round_box.add(self.round_label)
        
        self.rounds = []
        self.selected_round_idx = 0
        self.round_selector_label = arcade.gui.UILabel(text="Loading...", width=300, align="center")
        
        self.round_prev_btn = arcade.gui.UIFlatButton(text="<", width=30)
        self.round_prev_btn.on_click = self._on_prev_round
        self.round_next_btn = arcade.gui.UIFlatButton(text=">", width=30)
        self.round_next_btn.on_click = self._on_next_round
        
        self.round_selector_group = arcade.gui.UIBoxLayout(vertical=False, space_between=5)
        self.round_selector_group.add(self.round_prev_btn)
        self.round_selector_group.add(self.round_selector_label)
        self.round_selector_group.add(self.round_next_btn)
        
        self.round_box.add(self.round_selector_group)
        self.v_box.add(self.round_box)
        
        # --- Session Selection ---
        self.session_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)
        self.session_label = arcade.gui.UILabel(text="Session:", width=100, align="right")
        self.session_box.add(self.session_label)
        
        self.session_types = [
            ("Race", "R"),
            ("Qualifying", "Q"),
            ("Sprint", "S"),
            ("Sprint Qualifying", "SQ")
        ]
        self.selected_session_idx = 0
        self.session_selector_label = arcade.gui.UILabel(text=self.session_types[0][0], width=200, align="center")
        
        self.session_prev_btn = arcade.gui.UIFlatButton(text="<", width=30)
        self.session_prev_btn.on_click = self._on_prev_session
        self.session_next_btn = arcade.gui.UIFlatButton(text=">", width=30)
        self.session_next_btn.on_click = self._on_next_session
        
        self.session_selector_group = arcade.gui.UIBoxLayout(vertical=False, space_between=5)
        self.session_selector_group.add(self.session_prev_btn)
        self.session_selector_group.add(self.session_selector_label)
        self.session_selector_group.add(self.session_next_btn)
        
        self.session_box.add(self.session_selector_group)
        self.v_box.add(self.session_box)
        
        # --- Start Button ---
        self.start_button = arcade.gui.UIFlatButton(text="Start Replay", width=200)
        self.start_button.on_click = self.on_start_button_click
        self.v_box.add(self.start_button)
        
        # --- Loading Indicator ---
        self.loading_label = arcade.gui.UILabel(text="", text_color=arcade.color.YELLOW)
        self.v_box.add(self.loading_label)

        # Create a widget to hold the v_box widget, that will center the buttons
        anchor_layout = arcade.gui.UIAnchorLayout()
        anchor_layout.add(child=self.v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor_layout)
        
        # Initial Data Load
        self.schedule_cache = {}
        self.pending_schedule_data = None
        self.refresh_rounds()

    def _create_selector(self, initial_text, on_prev, on_next):
        box = arcade.gui.UIBoxLayout(vertical=False, space_between=5)
        prev_btn = arcade.gui.UIFlatButton(text="<", width=30)
        prev_btn.on_click = on_prev
        next_btn = arcade.gui.UIFlatButton(text=">", width=30)
        next_btn.on_click = on_next
        
        # We need to store the label to update it later. 
        # Since this is a helper, we'll assign it to self explicitly in the caller or use specific attributes.
        # For simplicity in this specific "Year" case:
        self.year_value_label = arcade.gui.UILabel(text=initial_text, width=100, align="center")
        
        box.add(prev_btn)
        box.add(self.year_value_label)
        box.add(next_btn)
        return box

    def _on_prev_year(self, event):
        idx = self.available_years.index(self.selected_year)
        if idx < len(self.available_years) - 1:
            self.selected_year = self.available_years[idx + 1]
            self.year_value_label.text = self.selected_year
            self.refresh_rounds()

    def _on_next_year(self, event):
        idx = self.available_years.index(self.selected_year)
        if idx > 0:
            self.selected_year = self.available_years[idx - 1]
            self.year_value_label.text = self.selected_year
            self.refresh_rounds()
            
    def refresh_rounds(self):
        year = int(self.selected_year)
        if year in self.schedule_cache:
            self._update_rounds_list(self.schedule_cache[year])
        else:
            self.loading_label.text = "Fetching Schedule..."
            self.round_selector_label.text = "Loading..."
            # Fetch in thread to avoid freezing UI
            thread = threading.Thread(target=self._fetch_schedule_thread, args=(year,))
            thread.start()
            
    def _fetch_schedule_thread(self, year):
        try:
            schedule = fastf1.get_event_schedule(year)
            # Filter for race events (exclude testing if needed, though get_event_schedule usually returns race rounds)
            # fastf1 3.0+ returns a DataFrame.
            # We want round number and event name.
            rounds_data = []
            
            # Iterate through DataFrame
            for i, row in schedule.iterrows():
                # Skip pre-season testing if RoundNumber is 0 or NaN
                if row['RoundNumber'] == 0:
                    continue
                rounds_data.append({
                    'round': row['RoundNumber'],
                    'name': row['EventName'],
                    'country': row['Country']
                })
            
            self.schedule_cache[year] = rounds_data
            
            # If the user hasn't changed the year while we were fetching
            if str(year) == self.selected_year:
                self.pending_schedule_data = rounds_data
                
        except Exception as e:
            print(f"Error fetching schedule: {e}")
            self.schedule_cache[year] = []
            if str(year) == self.selected_year:
                 self.pending_schedule_data = [] # signal empty/error

    def on_update(self, delta_time):
        if self.pending_schedule_data is not None:
             self._update_rounds_list(self.pending_schedule_data)
             self.pending_schedule_data = None

    def _update_rounds_list(self, rounds):
        self.rounds = rounds
        self.selected_round_idx = 0
        self.loading_label.text = ""
        self._update_round_label()

    def _update_round_label(self):
        if not self.rounds:
            self.round_selector_label.text = "No Events Found"
            return
            
        r = self.rounds[self.selected_round_idx]
        self.round_selector_label.text = f"Round {r['round']}: {r['name']}"

    def _on_prev_round(self, event):
        if not self.rounds: return
        self.selected_round_idx = (self.selected_round_idx - 1) % len(self.rounds)
        self._update_round_label()

    def _on_next_round(self, event):
        if not self.rounds: return
        self.selected_round_idx = (self.selected_round_idx + 1) % len(self.rounds)
        self._update_round_label()
        
    def _on_prev_session(self, event):
        self.selected_session_idx = (self.selected_session_idx - 1) % len(self.session_types)
        self.session_selector_label.text = self.session_types[self.selected_session_idx][0]

    def _on_next_session(self, event):
        self.selected_session_idx = (self.selected_session_idx + 1) % len(self.session_types)
        self.session_selector_label.text = self.session_types[self.selected_session_idx][0]

    def on_start_button_click(self, event):
        if not self.rounds:
            return
            
        selected_round = self.rounds[self.selected_round_idx]['round']
        selected_year = int(self.selected_year)
        selected_session_type = self.session_types[self.selected_session_idx][1]
        
        # Store result and close
        self.result = {
            'year': selected_year,
            'round': selected_round,
            'session_type': selected_session_type
        }
        self.close()

    def on_draw(self):
        self.clear()
        self.manager.draw()
        # Debug text to confirm window is drawing
        arcade.draw_text("Ver 1.0", 10, 10, arcade.color.GRAY, 10)

    def on_resize(self, width, height):
        super().on_resize(width, height)
        # Ensure manager knows about resize
        # (UIManager usually handles this via event hooks, but good to ensure)
        pass
