from typing import NamedTuple


class XYWH(NamedTuple):
    center_x: float
    center_y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.center_x - self.width / 2

    @property
    def right(self) -> float:
        return self.center_x + self.width / 2

    @property
    def bottom(self) -> float:
        return self.center_y - self.height / 2

    @property
    def top(self) -> float:
        return self.center_y + self.height / 2


def ensure_arcade_compat(arcade_module):
    if not hasattr(arcade_module, "XYWH"):
        arcade_module.XYWH = XYWH

    if not hasattr(arcade_module, "draw_rect_filled"):
        def draw_rect_filled(rect, color):
            arcade_module.draw_rectangle_filled(
                rect.center_x, rect.center_y, rect.width, rect.height, color
            )

        arcade_module.draw_rect_filled = draw_rect_filled

    if not hasattr(arcade_module, "draw_rect_outline"):
        def draw_rect_outline(rect, color, border_width=1):
            arcade_module.draw_rectangle_outline(
                rect.center_x,
                rect.center_y,
                rect.width,
                rect.height,
                color,
                border_width,
            )

        arcade_module.draw_rect_outline = draw_rect_outline

    if not hasattr(arcade_module, "draw_texture_rect"):
        def draw_texture_rect(rect, texture, angle=0, alpha=255):
            arcade_module.draw_texture_rectangle(
                rect.center_x,
                rect.center_y,
                rect.width,
                rect.height,
                texture,
                angle,
                alpha,
            )

        arcade_module.draw_texture_rect = draw_texture_rect

    if not hasattr(arcade_module, "draw_lrbt_rectangle_textured"):
        def draw_lrbt_rectangle_textured(left, right, bottom, top, texture):
            arcade_module.draw_texture_rectangle(
                (left + right) / 2,
                (bottom + top) / 2,
                right - left,
                top - bottom,
                texture,
            )

        arcade_module.draw_lrbt_rectangle_textured = draw_lrbt_rectangle_textured

    return arcade_module
