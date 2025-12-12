import os
import arcade
from src.interfaces.menu import F1Menu

# Kept these as "default" starting sizes, but they are no longer hard limits
SCREEN_WIDTH = 600
SCREEN_HEIGHT = 800
SCREEN_TITLE = "F1 Menu"

def run_menu(default_year=2025, default_round=12):
    window = F1Menu(default_year=default_year, default_round=default_round)
    arcade.run()

