import arcade
import time
from src.f1_data import enable_cache, load_session, get_quali_telemetry
from src.interfaces.qualifying import run_qualifying_replay

SCREEN_WIDTH = 600
SCREEN_HEIGHT = 800
SCREEN_TITLE = "F1 Menu"

# UI Constants
MENU_ITEM_SPACING = 40
MENU_ITEM_FONT_SIZE = 24
TITLE_FONT_SIZE = 36
MESSAGE_FONT_SIZE = 16
LOADING_WIDTH = 500
LOADING_HEIGHT = 300


class LoadingWindow(arcade.Window):
    """Loading screen window that displays while data is being loaded."""

    def __init__(self, message="Loading...", on_ready=None):
        """Initialize the loading window.

        Args:
            message: Loading message to display
            on_ready: Callback function to call after showing loading screen
        """
        super().__init__(LOADING_WIDTH, LOADING_HEIGHT, "Loading", resizable=False)
        arcade.set_background_color(arcade.color.BLACK)
        self.message = message
        self.spinner_angle = 0.0
        self.spinner_speed = 180.0  # degrees per second
        self.on_ready = on_ready
        self.elapsed_time = 0.0
        self.ready_called = False

    def on_draw(self):
        """Render the loading window."""
        self.clear()

        # Draw title
        arcade.draw_text(
            "F1 Race Replay",
            LOADING_WIDTH / 2,
            LOADING_HEIGHT - 60,
            arcade.color.WHITE,
            font_size=28,
            anchor_x="center",
            bold=True,
        )

        # Draw loading message
        arcade.draw_text(
            self.message,
            LOADING_WIDTH / 2,
            LOADING_HEIGHT / 2 + 20,
            arcade.color.CYAN,
            font_size=18,
            anchor_x="center",
            bold=True,
        )

        # Draw animated spinner
        spinner_radius = 30
        center_x = LOADING_WIDTH / 2
        center_y = LOADING_HEIGHT / 2 - 40

        # Draw spinner circle
        arcade.draw_circle_outline(
            center_x, center_y, spinner_radius, arcade.color.WHITE, 3
        )

        # Draw spinner indicator
        import math
        angle_rad = math.radians(self.spinner_angle)
        indicator_x = center_x + spinner_radius * math.cos(angle_rad)
        indicator_y = center_y + spinner_radius * math.sin(angle_rad)
        arcade.draw_circle_filled(
            indicator_x, indicator_y, 8, arcade.color.YELLOW
        )

        # Draw "Please wait..." text
        arcade.draw_text(
            "Please wait...",
            LOADING_WIDTH / 2,
            40,
            arcade.color.LIGHT_GRAY,
            font_size=14,
            anchor_x="center",
        )

    def on_update(self, delta_time):
        """Update the spinner animation and trigger ready callback."""
        self.spinner_angle += self.spinner_speed * delta_time
        if self.spinner_angle >= 360:
            self.spinner_angle -= 360

        # Call ready callback after showing loading screen briefly
        self.elapsed_time += delta_time
        if not self.ready_called and self.elapsed_time >= 0.5 and self.on_ready:
            self.ready_called = True
            self.on_ready()


class F1Menu(arcade.Window):
    """Main menu window for F1 Race Replay application."""

    def __init__(self, default_year=2025, default_round=12):
        """Initialize the F1 menu window.

        Args:
            default_year: Default year for race/qualifying sessions (default: 2025)
            default_round: Default round number for race/qualifying sessions (default: 12)
        """
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        arcade.set_background_color(arcade.color.BLACK)

        self.menu_items = ["Race Replay", "Qualifying", "Change Year", "Change Round", "Standings", "Exit"]
        self.menu_x = (SCREEN_WIDTH - 200) // 2
        self.menu_y = (SCREEN_HEIGHT - len(self.menu_items) * MENU_ITEM_SPACING) // 2
        self.font_size = MENU_ITEM_FONT_SIZE
        self.default_year = default_year
        self.default_round = default_round
        self.message = None
        self.message_timeout = 0
        self.editing_year = False
        self.editing_round = False
        # Store menu item bounding boxes for click detection
        self.menu_item_rects = []

    def on_draw(self):
        """Render the menu window."""
        self.clear()

        # Draw title
        arcade.draw_text(
            "F1 Race Replay",
            SCREEN_WIDTH / 2,
            SCREEN_HEIGHT - 80,
            arcade.color.WHITE,
            font_size=TITLE_FONT_SIZE,
            anchor_x="center",
            bold=True,
        )

        # Draw year and round info with highlight if editing
        year_color = arcade.color.YELLOW if self.editing_year else arcade.color.LIGHT_GRAY
        round_color = arcade.color.YELLOW if self.editing_round else arcade.color.LIGHT_GRAY
        
        year_text = f"{self.default_year}"
        round_text = f"Round {self.default_round}"
        year_x = SCREEN_WIDTH / 2 - 80
        round_x = SCREEN_WIDTH / 2 + 80
        info_y = SCREEN_HEIGHT - 130
        
        # Draw year with left/right arrows if editing
        if self.editing_year:
            # Left arrow button
            arcade.draw_triangle_filled(
                year_x - 30, info_y,
                year_x - 20, info_y - 8,
                year_x - 20, info_y + 8,
                arcade.color.WHITE
            )
            # Right arrow button
            arcade.draw_triangle_filled(
                year_x + 30, info_y,
                year_x + 20, info_y - 8,
                year_x + 20, info_y + 8,
                arcade.color.WHITE
            )
        
        arcade.draw_text(
            year_text,
            year_x,
            info_y,
            year_color,
            font_size=18,
            anchor_x="center",
            bold=self.editing_year,
        )
        
        arcade.draw_text(
            "Season -",
            SCREEN_WIDTH / 2 - 10,
            info_y,
            arcade.color.LIGHT_GRAY,
            font_size=14,
            anchor_x="center",
        )
        
        # Draw round with left/right arrows if editing
        if self.editing_round:
            # Left arrow button
            arcade.draw_triangle_filled(
                round_x - 50, info_y,
                round_x - 40, info_y - 8,
                round_x - 40, info_y + 8,
                arcade.color.WHITE
            )
            # Right arrow button
            arcade.draw_triangle_filled(
                round_x + 50, info_y,
                round_x + 40, info_y - 8,
                round_x + 40, info_y + 8,
                arcade.color.WHITE
            )
        
        arcade.draw_text(
            round_text,
            round_x,
            info_y,
            round_color,
            font_size=18,
            anchor_x="center",
            bold=self.editing_round,
        )

        # Draw menu items and store bounding boxes for click detection
        self.menu_item_rects = []
        for i, item in enumerate(self.menu_items):
            # Calculate bounding box for this menu item
            item_left = self.menu_x - 10
            item_right = self.menu_x + 300
            item_bottom = self.menu_y + i * MENU_ITEM_SPACING - 5
            item_top = self.menu_y + i * MENU_ITEM_SPACING + 25
            self.menu_item_rects.append((item_left, item_bottom, item_right, item_top))

            # Draw menu item background (hover effect area)
            arcade.draw_lrbt_rectangle_filled(
                left=item_left,
                right=item_right,
                bottom=item_bottom,
                top=item_top,
                color=(30, 30, 30, 200),
            )

            text = arcade.Text(
                item,
                self.menu_x,
                self.menu_y + i * MENU_ITEM_SPACING,
                arcade.color.LIGHT_GRAY,
                font_size=self.font_size,
                anchor_x="left",
                bold=False,
            )
            text.draw()

        # Draw instructions
        if self.editing_year:
            instruction = "Click arrows to change year, or click elsewhere to finish"
        elif self.editing_round:
            instruction = "Click arrows to change round, or click elsewhere to finish"
        else:
            instruction = "Click menu items to select"
        
        arcade.draw_text(
            instruction,
            SCREEN_WIDTH / 2,
            30,
            arcade.color.LIGHT_GRAY,
            font_size=12,
            anchor_x="center",
        )

        # Draw message if present
        if self.message:
            text = arcade.Text(
                self.message,
                SCREEN_WIDTH / 2,
                70,
                arcade.color.CYAN,
                font_size=MESSAGE_FONT_SIZE,
                anchor_x="center",
                bold=True,
            )
            text.draw()

    def on_update(self, delta_time):
        """Update game state each frame."""
        if self.message_timeout > 0:
            self.message_timeout -= delta_time
            if self.message_timeout <= 0:
                self.message = None

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        """Handle mouse clicks on menu items and year/round selectors.

        Args:
            x: Mouse x coordinate
            y: Mouse y coordinate
            button: Mouse button pressed
            modifiers: Modifier keys
        """
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        year_x = SCREEN_WIDTH / 2 - 80
        round_x = SCREEN_WIDTH / 2 + 80
        info_y = SCREEN_HEIGHT - 130

        # Handle clicks when editing year
        if self.editing_year:
            # Left arrow button (decrease year)
            if year_x - 30 <= x <= year_x - 20 and info_y - 10 <= y <= info_y + 10:
                self.default_year = max(2018, self.default_year - 1)
                return
            # Right arrow button (increase year)
            elif year_x + 20 <= x <= year_x + 30 and info_y - 10 <= y <= info_y + 10:
                import datetime
                max_year = datetime.datetime.now().year + 1
                self.default_year = min(max_year, self.default_year + 1)
                return
            # Clicking elsewhere cancels editing
            else:
                self.editing_year = False
                return

        # Handle clicks when editing round
        if self.editing_round:
            # Left arrow button (decrease round)
            if round_x - 50 <= x <= round_x - 40 and info_y - 10 <= y <= info_y + 10:
                self.default_round = max(1, self.default_round - 1)
                return
            # Right arrow button (increase round)
            elif round_x + 40 <= x <= round_x + 50 and info_y - 10 <= y <= info_y + 10:
                self.default_round = min(25, self.default_round + 1)
                return
            # Clicking elsewhere cancels editing
            else:
                self.editing_round = False
                return

        # Check if clicking on year selector (to start editing)
        if abs(x - year_x) < 50 and abs(y - info_y) < 15:
            self.editing_year = True
            self.editing_round = False
            return

        # Check if clicking on round selector (to start editing)
        if abs(x - round_x) < 60 and abs(y - info_y) < 15:
            self.editing_round = True
            self.editing_year = False
            return

        # Check if clicking on menu items
        for i, (left, bottom, right, top) in enumerate(self.menu_item_rects):
            if left <= x <= right and bottom <= y <= top:
                self.on_menu_select(i)
                return


    def show_message(self, text, duration=3.0):
        """Display a temporary message to the user.

        Args:
            text: Message text to display
            duration: How long to show the message in seconds
        """
        self.message = text
        self.message_timeout = duration

    def on_menu_select(self, item_index: int):
        """Handle menu item selection based on clicked item.

        Args:
            item_index: Index of the menu item that was clicked
        """
        if item_index == 0:
            return self.open_race_replay()
        elif item_index == 1:
            return self.open_qualifying()
        elif item_index == 2:
            # Change Year
            self.editing_year = True
            self.editing_round = False
        elif item_index == 3:
            # Change Round
            self.editing_round = True
            self.editing_year = False
        elif item_index == 4:
            return self.show_standings()
        elif item_index == 5:
            self.exit_menu()

    def open_race_replay(self):
        """Open race replay with default year and round."""
        # Close menu window
        self.close()

        # Show loading window
        loading_msg = f"Loading Race Replay \n{self.default_year} Season - Round {self.default_round}"
        
        # Create loading window
        loading_window = LoadingWindow(loading_msg)
        
        def load_data():
            # loading_window.close()
            try:
                # Import and run main function
                main = __import__("main").main
                main(self.default_year, self.default_round, "R")
            except Exception as e:
                # Show error in new menu window
                error_window = F1Menu(default_year=self.default_year, default_round=self.default_round)
                error_window.show_message(f"Error: {str(e)}", 5.0)
                arcade.run()

        loading_window.on_ready = load_data
        arcade.run()

    def open_qualifying(self):
        """Open qualifying replay with default year and round"""
        # Close menu window
        self.close()

        # Show loading window
        loading_msg = f"Loading Qualifying\n{self.default_year} Season - Round {self.default_round}"
        
        # Create loading window
        loading_window = LoadingWindow(loading_msg)
        
        def load_data():
            loading_window.close()
            try:
                # Enable cache
                enable_cache()

                # Load session
                session = load_session(self.default_year, self.default_round, "Q")

                # Get qualifying telemetry
                qualifying_session_data = get_quali_telemetry(session, session_type="Q")

                # Run the qualifying replay
                title = f"{session.event['EventName']} - Qualifying Results"
                run_qualifying_replay(
                    session=session,
                    data=qualifying_session_data,
                    title=title,
                )
            except Exception as e:
                # Show error in new menu window
                error_window = F1Menu(default_year=self.default_year, default_round=self.default_round)
                error_window.show_message(f"Error: {str(e)}", 5.0)
                arcade.run()

        loading_window.on_ready = load_data
        arcade.run()

    def show_standings(self):
        """Show championship standings (placeholder)"""
        self.show_message("Standings feature coming soon!", 3.0)

    def show_settings(self):
        """Show settings menu (placeholder)"""
        self.show_message("Settings feature coming soon!", 3.0)

    def exit_menu(self):
        """Exit the application"""
        arcade.close_window()


def run_menu(year=2025, round_number=12):
    """Run the F1 menu interface"""
    window = F1Menu(default_year=year, default_round=round_number)
    arcade.run()
