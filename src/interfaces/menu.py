
# GUI Menu System for F1 Race Replay

import arcade
import arcade.gui
import fastf1
from typing import Optional, Callable
from PIL import Image, ImageDraw
from src.f1_data import enable_cache

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
SCREEN_TITLE = "F1 Race Replay - Menu"


# btn texture
def make_button_texture(width, height, border_color, fill_color=(0, 0, 0, 0), border_width=2):
    texture = arcade.Texture.create_empty(
        f"btn_{width}x{height}_{border_color}", (width, height)
    )
    image = Image.new("RGBA", (width, height), fill_color)
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, width - 1, height - 1],
        outline=border_color,
        width=border_width
    )

    texture.image = image
    return texture


# menu
class MenuView(arcade.View):

    def __init__(self):
        super().__init__()
        self.manager = arcade.gui.UIManager()
        self.manager.enable()

        self.selected_year = 2025
        self.selected_round = 1
        self.selected_session = "R"

        self.available_rounds = []
        self.event_names = {}

        self.start_callback: Optional[Callable] = None

        self.status_text = ""
        self.status_color = arcade.color.LIGHT_GREEN
        self.status_text_obj = None

        self.year_input = None
        self.round_label = None

        arcade.set_background_color(arcade.color.BLACK)

    def setup(self, start_callback: Callable):
        self.start_callback = start_callback
        self.setup_ui()
        # Don't auto-load rounds on startup - wait for user to click "Load Year"

    def setup_ui(self):

        # textures
        btn_normal = make_button_texture(120, 40, arcade.color.WHITE, border_width=0)
        btn_hover = make_button_texture(120, 40, arcade.color.LIGHT_GREEN, border_width=0)
        btn_pressed = make_button_texture(120, 40, arcade.color.YELLOW, border_width=0)

        start_normal = make_button_texture(350, 60, arcade.color.WHITE, border_width=0)
        start_hover = make_button_texture(350, 60, arcade.color.LIGHT_GREEN, border_width=0)
        start_pressed = make_button_texture(350, 60, arcade.color.YELLOW, border_width=0)

        v_box = arcade.gui.UIBoxLayout(space_between=20)

        # title
        v_box.add(
            arcade.gui.UILabel(
                text="F1 RACE REPLAY",
                font_size=36,
                bold=True,
                text_color=arcade.color.WHITE
            )
        )

        v_box.add(
            arcade.gui.UILabel(
                text="Select race parameters to begin",
                font_size=14,
                text_color=arcade.color.LIGHT_GRAY
            )
        )

        v_box.add(arcade.gui.UISpace(height=20))

        # year 
        v_box.add(arcade.gui.UILabel(text="Year:", font_size=16, bold=True, text_color=arcade.color.WHITE))

        year_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)

        self.year_input = arcade.gui.UIInputText(
            text=str(self.selected_year),
            width=150,
            height=40,
            font_size=16
        )
        year_box.add(self.year_input)

        year_btn = arcade.gui.UITextureButton(
            text="Load Year",
            texture=btn_normal,
            texture_hovered=btn_hover,
            texture_pressed=btn_pressed
        )
        year_btn.on_click = self._load_year_from_input
        year_box.add(year_btn)

        v_box.add(year_box)

        # round
        self.round_label = arcade.gui.UILabel(
            text="Click 'Load Year' to begin",
            font_size=16,
            bold=True,
            text_color=arcade.color.LIGHT_GRAY
        )
        v_box.add(self.round_label)

        nav_box = arcade.gui.UIBoxLayout(vertical=False, space_between=15)

        prev_btn = arcade.gui.UITextureButton(
            text="◄ Prev",
            texture=btn_normal,
            texture_hovered=btn_hover,
            texture_pressed=btn_pressed
        )
        prev_btn.on_click = self._prev_round

        next_btn = arcade.gui.UITextureButton(
            text="Next ►",
            texture=btn_normal,
            texture_hovered=btn_hover,
            texture_pressed=btn_pressed
        )
        next_btn.on_click = self._next_round

        nav_box.add(prev_btn)
        nav_box.add(next_btn)
        v_box.add(nav_box)

        # session
        v_box.add(arcade.gui.UILabel(text="Session:", font_size=16, bold=True, text_color=arcade.color.WHITE))

        session_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)
        sessions = [("Race", "R"), ("Sprint", "S"), ("Quali", "Q"), ("Sprint Q", "SQ")]

        for name, code in sessions:
            btn = arcade.gui.UITextureButton(
                text=name,
                texture=btn_normal,
                texture_hovered=btn_hover,
                texture_pressed=btn_pressed
            )
            btn.on_click = self._create_session_handler(code)
            session_box.add(btn)

        v_box.add(session_box)

        v_box.add(arcade.gui.UISpace(height=10))

        # start btn
        start_btn = arcade.gui.UITextureButton(
            text="START REPLAY",
            texture=start_normal,
            texture_hovered=start_hover,
            texture_pressed=start_pressed
        )
        start_btn.on_click = self._on_start_clicked

        v_box.add(start_btn)

        anchor = arcade.gui.UIAnchorLayout()
        anchor.add(v_box, anchor_x="center_x", anchor_y="center_y")
        self.manager.add(anchor)

    # logic
    def _load_year_from_input(self, event):
        try:
            year = int(self.year_input.text)
            if not (2018 <= year <= 2025):
                raise ValueError
            self.selected_year = year
            self.status_text = f"Loading rounds for {year}..."
            self.status_color = arcade.color.YELLOW
            self._update_status_text()
            self.load_available_rounds(year)
        except ValueError:
            self.status_text = "Invalid year. Please enter 2018-2025"
            self.status_color = arcade.color.RED
            self._update_status_text()

    def _create_session_handler(self, code):
        def handler(event):
            self.selected_session = code
            session_names = {"R": "Race", "S": "Sprint", "Q": "Qualifying", "SQ": "Sprint Qualifying"}
            self.status_text = f"Selected: {session_names.get(code, code)}"
            self.status_color = arcade.color.LIGHT_GREEN
            self._update_status_text()
        return handler

    def _prev_round(self, event):
        if self.available_rounds:
            i = self.available_rounds.index(self.selected_round)
            if i > 0:
                self.selected_round = self.available_rounds[i - 1]
                self._update_round_display()

    def _next_round(self, event):
        if self.available_rounds:
            i = self.available_rounds.index(self.selected_round)
            if i < len(self.available_rounds) - 1:
                self.selected_round = self.available_rounds[i + 1]
                self._update_round_display()

    def _update_round_display(self):
        name = self.event_names.get(self.selected_round, "")
        self.round_label.text = f"Round {self.selected_round}: {name}"
        self.round_label.fit_content()

    def load_available_rounds(self, year):
        try:
            enable_cache()
            schedule = fastf1.get_event_schedule(year)
            self.available_rounds = []
            self.event_names = {}

            for _, e in schedule.iterrows():
                round_num = e["RoundNumber"]
                # Skip round 0 (Pre-Season Testing)
                if round_num == 0:
                    continue
                self.available_rounds.append(round_num)
                self.event_names[round_num] = e["EventName"]

            if self.available_rounds:
                self.selected_round = self.available_rounds[0]
                self._update_round_display()

            self.status_text = f"Loaded {len(self.available_rounds)} rounds for {year}"
            self.status_color = arcade.color.LIGHT_GREEN
            self._update_status_text()
        except Exception as e:
            self.status_text = f"Error: No data available for {year}. Choose 2018-2025"
            self.status_color = arcade.color.RED
            self._update_status_text()

    def _on_start_clicked(self, event):
        if self.start_callback:
            self.status_text = "Starting replay..."
            self.status_color = arcade.color.YELLOW
            self._update_status_text()
            
            self.start_callback(
                year=self.selected_year,
                round_number=self.selected_round,
                session_type=self.selected_session,
                refresh_data=False,
                enable_chart=False
            )

    def _update_status_text(self):
        self.status_text_obj = arcade.Text(
            self.status_text,
            SCREEN_WIDTH // 2,
            25,
            self.status_color,
            font_size=11,
            anchor_x="center"
        )

    def on_draw(self):
        self.clear()
        self.manager.draw()
        if self.status_text_obj:
            self.status_text_obj.draw()

    def on_hide_view(self):
        """Disable manager when view is hidden"""
        self.manager.disable()

    def on_show_view(self):
        """Enable manager when view is shown"""
        self.manager.enable()


# entry to menu
def show_menu(start_callback: Callable):
    window = arcade.get_window()
    window.set_size(SCREEN_WIDTH, SCREEN_HEIGHT)
    window.set_caption(SCREEN_TITLE)

    view = MenuView()
    view.setup(start_callback)
    window.show_view(view)
