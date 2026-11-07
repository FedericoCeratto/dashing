"""
Basic unit tests
"""

import blessed
import pyte
import pytest

import dashing as da
from dashing import RGB


def test_col():
    assert da.color_rgb("#32e60b") == RGB(50, 230, 11)
    assert da.color_rgb("*00a0FF") == RGB(255, 95, 95)
    assert da.color_rgb(rgb=(50, 230, 11)) == RGB(50, 230, 11)
    assert da.color_rgb(hsv=(0.1, 0.1, 0.1)) == RGB(25, 24, 22)
    with pytest.raises(Exception):
        da.color_rgb()


def _render(tile, w, h):
    """Render a tile on a w x h pyte screen and return the screen lines"""

    t = blessed.Terminal(kind="xterm-256color", force_styling=True)
    buf = da._Buf()
    tile._display(buf, da.TBox(t, 0, 0, w, h))
    screen = pyte.Screen(w, h)
    pyte.Stream(screen).feed("".join(buf._buf))
    return screen.display


def test_vchart_full():
    ch = da.VChart(border=False)
    for _ in range(50):
        ch.append(100)

    exp = ["▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉"]
    assert _render(ch, 20, 1) == exp


def test_vchart_fraction():
    ch = da.VChart(border=False)
    for _ in range(50):
        ch.append(49.5)

    exp = ["▉▉▉▉▉▉▉▉▉▉          "]
    assert _render(ch, 20, 1) == exp
