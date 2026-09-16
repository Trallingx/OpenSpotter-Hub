"""
Helper Functions
Common utility functions for the application.
"""

from typing import Tuple
import math


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between min and max.

    Args:
        value: Value to clamp
        min_val: Minimum value
        max_val: Maximum value

    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Calculate Euclidean distance between two points.

    Args:
        x1, y1: First point
        x2, y2: Second point

    Returns:
        Distance
    """
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def create_color_palette(num_colors: int) -> list:
    """
    Create a palette of distinct colors using HSV color space.

    Args:
        num_colors: Number of colors to generate

    Returns:
        List of RGB tuples (r, g, b) in range [0, 255]
    """
    colors = []
    for i in range(num_colors):
        h = (i / num_colors) * 360  # Hue
        s = 100  # Saturation
        v = 100  # Value
        rgb = hsv_to_rgb(h, s, v)
        colors.append(rgb)
    return colors


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    """
    Convert HSV color to RGB.

    Args:
        h: Hue (0-360)
        s: Saturation (0-100)
        v: Value (0-100)

    Returns:
        RGB tuple (r, g, b) in range [0, 255]
    """
    h = h % 360
    s = s / 100.0
    v = v / 100.0

    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)

    return (r, g, b)


def format_position(x: float, y: float, z: float, precision: int = 2) -> str:
    """
    Format position as string.

    Args:
        x, y, z: Coordinates
        precision: Decimal places

    Returns:
        Formatted string
    """
    return f"X={x:.{precision}f} Y={y:.{precision}f} Z={z:.{precision}f}"


def format_progress(current: int, total: int) -> str:
    """
    Format progress as string.

    Args:
        current: Current progress
        total: Total

    Returns:
        Formatted string
    """
    if total == 0:
        return "0%"
    percent = (current / total) * 100
    return f"{percent:.1f}%"
