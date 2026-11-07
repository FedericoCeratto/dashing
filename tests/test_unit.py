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


def _screen(tile, w, h):
    """Render a tile on a w x h pyte screen and return the screen"""

    t = blessed.Terminal(kind="xterm-256color", force_styling=True)
    # Force truecolor to get exact RGB values instead of the nearest palette color
    t.number_of_colors = 1 << 24
    buf = da._Buf()
    tile._display(buf, da.TBox(t, 0, 0, w, h))
    screen = pyte.Screen(w, h)
    pyte.Stream(screen).feed("".join(buf._buf))
    return screen


def _render(tile, w, h):
    """Render a tile on a w x h pyte screen and return the screen lines"""
    return _screen(tile, w, h).display


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


def test_hgauge_colors():
    g = da.HGauge(val=60, border_color="#00ff00", color_low="#ff0000", color_high="#0000ff")
    s = _screen(g, 12, 3)
    row = [s.buffer[1][x] for x in range(12)]

    assert s.display[1] == "│▉▉▉▉▉▉▏▏▏▏│"

    exp = [
        "00ff00",  # green border
        "ff0000",  # gradient from red
        "ff7100",
        "ffe200",
        "aaff00",
        "38ff00",
        "00ff38",
        "00ff38",
        "808080",  # default color
        "808080",
        "808080",
        "00ff00",  # green border
    ]
    assert [c.fg for c in row] == exp

    # the background is never set
    assert {s.buffer[y][x].bg for y in range(3) for x in range(12)} == {"default"}


def test_reset_color(capsys):
    t = blessed.Terminal(kind="xterm-256color", force_styling=True)
    t.number_of_colors = 1 << 24
    ui = da.HSplit(da.Text("hi", color="#ff0000"), border_color="#00ff00")
    ui.display(t)

    screen = pyte.Screen(t.width, t.height)
    pyte.Stream(screen).feed(capsys.readouterr().out)
    assert screen.cursor.attrs.fg == "default"
    assert screen.cursor.attrs.bg == "default"


def test_hgauge_full():
    g = da.HGauge(val=100, border=False)
    assert _render(g, 20, 1) == ["▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉"]


def test_hgauge_over_100():
    g = da.HGauge(val=112, border=False)
    assert _render(g, 20, 1) == ["▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉"]


def test_hgauge_empty():
    g = da.HGauge(val=0, border=False)
    assert _render(g, 20, 1) == ["▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏"]


def test_hgauge_negative():
    g = da.HGauge(val=-10, border=False)
    assert _render(g, 20, 1) == ["▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏▏"]


def test_hgauge_label_full():
    g = da.HGauge(label="label", val=100, border=False)
    assert _render(g, 20, 1) == ["label ▉▉▉▉▉▉▉▉▉▉▉▉▉▉"]


def test_hgauge_label_over_100():
    g = da.HGauge(label="label", val=112, border=False)
    assert _render(g, 20, 1) == ["label ▉▉▉▉▉▉▉▉▉▉▉▉▉▉"]


def test_hgauge_label_empty():
    g = da.HGauge(label="label", val=0, border=False)
    assert _render(g, 20, 1) == ["label ▏▏▏▏▏▏▏▏▏▏▏▏▏▏"]


def test_vgauge_full():
    g = da.VGauge(val=100, border=False)
    assert _render(g, 3, 4) == ["███", "███", "███", "███"]


def test_vgauge_over_100():
    g = da.VGauge(val=112, border=False)
    assert _render(g, 3, 4) == ["███", "███", "███", "███"]


def test_vgauge_half():
    g = da.VGauge(val=50, border=False)
    assert _render(g, 3, 4) == ["   ", "   ", "███", "███"]


def test_vgauge_empty():
    g = da.VGauge(val=0, border=False)
    assert _render(g, 3, 4) == ["   ", "   ", "   ", "▁▁▁"]


def test_vgauge_negative():
    g = da.VGauge(val=-10, border=False)
    assert _render(g, 3, 4) == ["   ", "   ", "   ", "▁▁▁"]
