"""
Dashing allows to quickly create terminal-based dashboards in Python.

It focuses on practicality over completeness. If you want to have complete control
over every character on the screen use ncurses or similar.

Dashing automatically fills the screen with "tiles".

There are 2 type of "container" tiles that allow vertical and horizontal splitting
called ``VSplit`` and ``HSplit``. Dashing scales them based on the screen size.

Any tile passed as argument at init time will be nested using the ``.items`` attribute

``.items`` can be used to access, add or remove nested tiles.

You can easily extend Dashing with new tile types. Subclass :class:`Tile`, implement
``__init__`` and ``_display``.

The other types of tiles are:
    - :class:`Text` - simple text
    - :class:`Log` - a log pane that scrolls automatically
    - :class:`HGauge` - horizontal gauge
    - :class:`VGauge` - vertical gauge
    - :class:`VChart` - vertical chart
    - :class:`HChart` - horizontal chart
    - :class:`HBrailleChart`
    - :class:`HBrailleFilledChart`

All tiles accept ``title``, and ``theme`` keywords arguments at init time.
 ``color``, ``border_color``

Gauges represent an instant value between 0 and 100.
You can set a value at init time using the ``val`` keyword argument or access the
``.value`` attribute at any time.

Charts represent a sequence of values between 0 and 100 and scroll automatically.

Call :meth:`display` on the root element to display or update the ui.

You can easily nest splits and tiles as in::

    from dashing import HSplit, VSplit, HGauge, open_terminal

    ui = HSplit(
            VSplit(
                HGauge(val=50, title="foo", border_color=5),
            )
        )
    # access a tile by index
    gauge = ui.items[0].items[0]
    gauge.value = 3.0

    # create a terminal session (cleans up screen afterwards):
    with open_terminal() as terminal:
        # display/refresh the ui
        ui.display(terminal)
        # sleep for reasonable fps and less flicker
        time.sleep(1 / 30)
"""

# TODO add tree display for debugging

__version__ = "0.2.0"

import colorsys
import contextlib
from collections import namedtuple, deque
import itertools
import warnings
from typing import Literal, Optional, Tuple, Generator, List, Union

from blessed import Terminal

# # "graphic" elements # #

border_bl = "└"
border_br = "┘"
border_tl = "┌"
border_tr = "┐"
border_h = "─"
border_v = "│"
hbar_elements = ("▏", "▎", "▍", "▌", "▋", "▊", "▉")
vbar_elements = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")
braille_left = (0x01, 0x02, 0x04, 0x40, 0)
braille_right = (0x08, 0x10, 0x20, 0x80, 0)
braille_r_left = (0x04, 0x02, 0x01)
braille_r_right = (0x20, 0x10, 0x08)

# Note: Coords start from top left.
#   `x` is vertical       `h` is height
#   `y` is horizontal     `w` is width
#
# TODO: The sequence x y w h is not intuitive :-/
TBox = namedtuple("TBox", "t x y w h")


# # Color management # #


class RGB:
    """An RGB color, stored as 3 integers"""

    __slots__ = ["r", "g", "b"]

    def __init__(self, r: int, g: int, b: int) -> None:
        self.r = r
        self.g = g
        self.b = b

    def __iter__(self):
        yield self.r
        yield self.g
        yield self.b

    @classmethod
    def parse(cls, color: str):
        """Parse color expressed in different formats and return an RGB object
        Formats:
            color("#RRGGBB") RGB in hex
            color("*HHSSVV") HSV in hex with values ranging 00 to FF
        """
        if color.startswith("#"):
            return cls(int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))

        if color.startswith("*"):
            h = int(color[1:3], 16) / 255.0
            s = int(color[3:5], 16) / 255.0
            v = int(color[5:7], 16) / 255.0
            return cls(*(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)))

        raise ValueError("Invalid color")

    @classmethod
    def from_hsv(cls, h: float, s: float, v: float):
        """Create an RGB instance from HSV values"""
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return cls(int(r * 255), int(g * 255), int(b * 255))

    def to_hls(self) -> Tuple[float, float, float]:
        """Convert to HLS"""
        return colorsys.rgb_to_hls(self.r, self.g, self.b)

    def __eq__(self, other) -> bool:
        """Compares 2 colors for equality"""
        if isinstance(other, self.__class__):
            return (self.r, self.g, self.b) == (other.r, other.g, other.b)
        return False

    def __ne__(self, other) -> bool:
        """Compares 2 colors for not-equality"""
        return not self.__eq__(other)

    def pr(self, term) -> str:
        """Returns a printable string element"""
        return term.color_rgb(self.r, self.g, self.b)


# "int" is legacy
Color = Union[int, str, None, RGB]


def color_rgb(
    color: str = "",
    rgb: Optional[Tuple[int, int, int]] = None,
    hsv: Optional[Tuple[float, float, float]] = None,
) -> RGB:
    """Parse color expressed in different formats and return RGB values
    Formats:
        color("#RRGGBB") RGB in hex
        color(rgb=(1, 20, 8)) RGB as integers
        color("*HHSSVV") HSV in hex with values ranging 00 to FF
        color(hsv=(.5, .2, .7)) HSV as floats
    """
    if color:
        return RGB.parse(color)

    if hsv is not None:
        return RGB.from_hsv(*hsv)

    if rgb is None:
        raise ValueError("Either color, rgb or hsv should have a value")

    return RGB(*rgb)


def _parsecol(col: RGB | str) -> RGB:
    return col if isinstance(col, RGB) else RGB.parse(col)


def _initcol(col: None | int | RGB | str) -> RGB | None:
    if col is None:
        return None
    if isinstance(col, RGB):
        return col
    if isinstance(col, str):
        return RGB.parse(col)
    if isinstance(col, int):
        warnings.warn("ANSI colors are deprecated", DeprecationWarning)
        lookup = [
            (0, 0, 0),
            (255, 0, 0),
            (0, 255, 0),
            (255, 255, 0),
            (0, 0, 255),
            (255, 0, 255),
            (0, 255, 255),
            (255, 255, 255),
        ]
        return RGB(*lookup[col])

    raise ValueError("Unexpected color type", type(col))


def interpolate_colors(high: RGB, low: RGB, steps: int, pos) -> RGB:
    """Interpolate between 2 colors. Used to generate gradients."""
    assert steps > 0
    start = high.to_hls()
    end = low.to_hls()

    start = colorsys.rgb_to_hsv(*low)
    end = colorsys.rgb_to_hsv(*high)

    # Interpolate HSL components
    k = pos / float(steps)
    h = start[0] + (end[0] - start[0]) * k
    s = start[1] + (end[1] - start[1]) * k
    v = start[2] + (end[2] - start[2]) * k

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    assert r >= 0
    assert r <= 255, r

    return RGB(int(r), int(g), int(b))


# # Tiles # #

# Tiles are instantiated bottom up in order to support a friendly declarative style.
# During display() the tree is walked recursively starting from the root.
# Intermediate Tile nodes are only HSplit and VSplit. Every other type of Tile is a leaf.


class _Buf:
    """Output buffer for internal use"""

    __slots__ = ["_buf"]

    def __init__(self) -> None:
        self._buf: List[str] = []

    def add(self, *i: str) -> None:
        """Append string to buffer"""
        self._buf.extend(i)

    def print(self) -> None:
        """Render buffer on screen"""
        print("".join(self._buf))


class Tile:
    """Base class for all Dashing tiles."""

    def __init__(
        self,
        title: str = "",
        border: bool = True,
        border_color: Color = None,
        color: Color = None,
        color_high: Color = None,
        color_low: Color = None,
    ) -> None:
        """
        :param title: Title of the tile
        :param border_color: Setting this will enable a
         border and shrinks available size by 1 character on each side.
        :param color: Color of the text inside the tile.
        """
        self.title = title
        self._terminal: Optional[Terminal] = None
        self.parent: Optional[Tile] = None
        self.items: List[Tile] = []

        self.border = border  # bool
        self._text_color = _initcol(color)
        self._border_color = _initcol(border_color)
        self._color_high = _initcol(color_high)
        self._color_low = _initcol(color_low)

    def _inherit_style(self, name: str) -> RGB:
        priv = f"_{name}"
        if getattr(self, priv):
            return getattr(self, priv)
        elif self.parent:
            return getattr(self.parent, name)
        else:
            # I'm the root element
            col = RGB(128, 128, 128)
            setattr(self, priv, col)
            return col

    @property
    def text_color(self) -> RGB:
        """Get the text color. Walk upwards in the UI tree until a value is found."""
        return self._inherit_style("text_color")

    @property
    def border_color(self) -> RGB:
        """Get the border color. Walk upwards in the UI tree until a value is found."""
        return self._inherit_style("border_color")

    @property
    def color_high(self) -> RGB:
        """Get the chart high value color. Walk upwards in the UI tree until a value is found."""
        return self._inherit_style("color_high")

    @property
    def color_low(self) -> RGB:
        """Get the chart low value color. Walk upwards in the UI tree until a value is found."""
        return self._inherit_style("color_low")

    def set_color(self, name: str, value: str | RGB | None) -> None:
        """Set color by attribute name. If set to None it removes the existing color (if any) enabling inheritance
        from parent tiles.
        """
        if name not in ("text_color", "border_color", "color_high", "color_low"):
            raise ValueError(f"Invalid color name {name}")

        if isinstance(value, str):
            value = RGB.parse(value)

        if isinstance(value, RGB | None):
            setattr(self, f"_{name}", value)
            return

        raise ValueError(f"Invalid color type {type(value)}")

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        """
        Implement this method when subclassing :class:`.Tile`, to fill in the available space outlined by
        the ``tbox`` with the tile content.
        """
        raise NotImplementedError

    def _draw_borders_and_title(self, buf: _Buf, tbox: TBox) -> TBox:
        """
        Draw borders and title as needed and returns
        inset (x, y, width, height)
        """
        if self.border:
            buf.add(self.border_color.pr(tbox.t))
            # left and right
            for dx in range(1, tbox.h - 1):
                buf.add(tbox.t.move(tbox.x + dx, tbox.y) + border_v)
                buf.add(tbox.t.move(tbox.x + dx, tbox.y + tbox.w - 1) + border_v)
            # bottom
            buf.add(
                tbox.t.move(tbox.x + tbox.h - 1, tbox.y),
                border_bl,
                border_h * (tbox.w - 2),
                border_br,
            )
            if self.title:
                # top border with title
                margin = int((tbox.w - len(self.title)) / 20)
                border_t = (
                    border_h * (margin - 1) + " " * margin + self.title + " " * margin
                )
                border_t += (tbox.w - len(border_t) - 2) * border_h
            else:
                # top border without title
                border_t = border_h * (tbox.w - 2)

            # top
            buf.add(tbox.t.move(tbox.x, tbox.y), border_tl, border_t, border_tr)

        elif self.title:
            # top title without border
            margin = int((tbox.w - len(self.title)) / 20)

            title = (
                " " * margin + self.title + " " * (tbox.w - margin - len(self.title))
            )
            buf.add(tbox.t.move(tbox.x, tbox.y) + title)

        if self.border:
            return TBox(tbox.t, tbox.x + 1, tbox.y + 1, tbox.w - 2, tbox.h - 2)

        elif self.title:
            return TBox(tbox.t, tbox.x + 1, tbox.y, tbox.w - 0, tbox.h - 1)

        return TBox(tbox.t, tbox.x, tbox.y, tbox.w, tbox.h)

    def _fill_area(self, buf: _Buf, tbox: TBox, char: str) -> None:
        """Fill area with a character"""
        for dx in range(0, tbox.h):
            buf.add(tbox.t.move(tbox.x + dx, tbox.y) + char * tbox.w)

    def _fill_screen_with_symbol(self, buf: _Buf) -> None:
        """Used for debugging"""
        t = Terminal()
        tbox = TBox(t, 0, 0, t.width, t.height)
        self._fill_area(buf, tbox, "@")

    def display(self, terminal: Optional[Terminal] = None) -> None:
        """Render current tile and its items. Recurse into nested splits if any."""
        if self._terminal is None:
            self._terminal = terminal or Terminal()

        t = self._terminal
        tbox = TBox(t, 0, 0, t.width, t.height - 1)

        # Recurse into nested splits filling `buf`
        buf = _Buf()
        self._display(buf, tbox)

        # park cursor in a safe place and reset color
        buf.add(t.move(t.height - 3, 0), self.border_color.pr(t))

        # Print the whole thing
        buf.print()


class Split(Tile):
    """Split a box vertically (VSplit) or horizontally (HSplit)

    Splits create a hierarchy of UI elements
    By defaults splits have no borders.
    Initialize them with border=True to add it.
    """

    def __init__(self, *items: Tile, border=False, **kw) -> None:
        # `border = False` is the default for Split. Pass it to super().__init__
        kw["border"] = border
        super().__init__(**kw)
        self.items: List[Tile] = list(items)
        self.update_children()

    def update_children(self) -> None:
        """Pass down the theming to children tiles and set the `parent` attribute
        Also connect the buffers
        """
        for i in self.items:
            i.parent = self


class VSplit(Split):
    """Vertical Split"""

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        """Render current tile and its items. Recurse into nested splits"""
        tbox = self._draw_borders_and_title(buf, tbox)
        if not self.items:
            # empty split
            # self._fill_area(tbox, " ")
            return

        item_height = tbox.h // len(self.items)
        item_width = tbox.w

        x = tbox.x
        for i in self.items:
            i._display(buf, TBox(tbox.t, x, tbox.y, item_width, item_height))
            x += item_height

        # Fill leftover area
        leftover_x = tbox.h - x + 1
        if leftover_x > 0:
            self._fill_area(buf, TBox(tbox.t, x, tbox.y, tbox.w, leftover_x), " ")


class HSplit(Split):
    """Horizontal Split"""

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        """Render current tile and its items. Recurse into nested splits"""
        # apply default theme on root element
        tbox = self._draw_borders_and_title(buf, tbox)
        if not self.items:
            # empty split
            # self._fill_area(tbox, " ")
            return

        item_height = tbox.h
        item_width = tbox.w // len(self.items)

        y = tbox.y
        for i in self.items:
            i._display(buf, TBox(tbox.t, tbox.x, y, item_width, item_height))
            y += item_width

        # Fill leftover area
        leftover_y = tbox.w - y + 1
        if leftover_y > 0:
            self._fill_area(buf, TBox(tbox.t, tbox.x, y, leftover_y - 1, tbox.h), " ")


class Text(Tile):
    """
    A multi-line text box. Example::

       Text('Hello World, this is dashing.', border_color=2),

    """

    def __init__(self, text: str, color: Color = None, **kw) -> None:
        super().__init__(**kw)
        self.text: str = text

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(buf, tbox)
        for dx, line in _pad(self.text.splitlines()[-(tbox.h) :], tbox.h):
            buf.add(
                self.text_color.pr(tbox.t),
                tbox.t.move(tbox.x + dx, tbox.y),
                line,
                " " * (tbox.w - len(line)),
            )


class Log(Tile):
    """A log pane that scrolls automatically.
    Add new lines with :meth:`append`
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.logs: deque = deque(maxlen=50)

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        # TODO: support low -> high -> low gradient
        tbox = self._draw_borders_and_title(buf, tbox)
        n_logs = len(self.logs)
        log_range = min(n_logs, tbox.h)
        start = n_logs - log_range

        for dx, line in _pad((self.logs[ln] for ln in range(start, n_logs)), tbox.h):
            col = interpolate_colors(self.color_high, self.color_low, tbox.h, dx)
            buf.add(
                col.pr(tbox.t),
                tbox.t.move(tbox.x + dx, tbox.y),
                line,
                " " * (tbox.w - len(line)),
            )

    def append(self, msg: str) -> None:
        """Append a new log message at the bottom"""
        self.logs.append(msg)


class HGauge(Tile):
    """Horizontal gauge"""

    def __init__(self, label: str = "", val=100, color: Color = None, **kw) -> None:
        super().__init__(color=color, **kw)
        self.value = val
        self.label = label

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(buf, tbox)
        #
        # <------------------- tbox.w ---------------------->
        # <-- label_wid --><-- bar_iwid --><-- filler_wid -->
        #
        if self.label:
            label_wid = len(self.label)
            bar_wid = (tbox.w - label_wid - 3) * self.value / 100
            v_center = int((tbox.h) * 0.5)
            bar_iwid = int(bar_wid)
            filler_wid = tbox.w - bar_iwid - label_wid - 2

        else:
            label_wid = 0
            bar_wid = tbox.w * self.value / 100.0
            v_center = None
            bar_iwid = int(bar_wid)
            filler_wid = tbox.w - bar_iwid - 1

        # Stores a row of the gauge (colored bar + filler)
        blk: List[str] = []

        # Fill the colored part
        for pos in range(bar_iwid):
            col = interpolate_colors(
                self.color_high, self.color_low, (bar_iwid + filler_wid), pos
            )
            blk.append(col.pr(tbox.t))
            blk.append(hbar_elements[-1])  # full element

        # Pick the char for the partially-filled element
        selector = int((bar_wid - int(bar_wid)) * 7)
        blk.append(hbar_elements[selector])

        # Fill the remaining part with thin lines
        blk.append(self.text_color.pr(tbox.t))
        blk.append(hbar_elements[0] * filler_wid)

        # Assemble the pieces
        for dx in range(0, tbox.h):
            m = tbox.t.move(tbox.x + dx, tbox.y)
            if self.label:
                if dx == v_center:
                    # draw label
                    buf.add(m + self.label + " ")
                else:
                    buf.add(m + " " * label_wid + " ")
            else:
                buf.add(m)

            buf.add(*blk)


class VGauge(Tile):
    """Vertical gauge"""

    def __init__(self, val=100, color: Color = None, **kw) -> None:
        super().__init__(color=color, **kw)
        self.value = val

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        """Render current tile"""
        tbox = self._draw_borders_and_title(buf, tbox)
        nh = tbox.h * (self.value / 100.5)
        buf.add(tbox.t.move(tbox.x, tbox.y) + self.text_color.pr(tbox.t))
        for dx in range(tbox.h):
            m = tbox.t.move(tbox.x + tbox.h - dx - 1, tbox.y)
            buf.add(m)
            col = interpolate_colors(self.color_high, self.color_low, tbox.h, dx)
            buf.add(col.pr(tbox.t))
            if dx < int(nh):
                # full element
                buf.add(vbar_elements[-1] * tbox.w)
            elif dx == int(nh):
                # fractional element
                index = int((nh - int(nh)) * 8)
                buf.add(vbar_elements[index] * tbox.w)
            else:
                buf.add(" " * tbox.w)


class VChart(Tile):
    """Vertical chart. Values must be between 0 and 100 and can be float."""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=50)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        filled_element = hbar_elements[-1]
        scale = tbox.w / 100.0
        buf.add(self.text_color.pr(tbox.t))
        for dx in range(tbox.h):
            index = 50 - (tbox.h) + dx
            try:
                dp = self.datapoints[index] * scale
                index = int((dp - int(dp)) * 8)
                bar = filled_element * int(dp) + hbar_elements[index]
                assert len(bar) <= tbox.w, dp
                bar += " " * (tbox.w - len(bar))
            except IndexError:
                bar = " " * tbox.w
            buf.add(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HChart(Tile):
    """Horizontal chart, filled"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(buf, tbox)
        buf.add(self.text_color.pr(tbox.t))
        for dx in range(tbox.h):
            bar = ""
            for dy in range(tbox.w):
                dp_index = -tbox.w + dy
                try:
                    dp = self.datapoints[dp_index]
                    q = (1 - dp / 100) * tbox.h
                    if dx == int(q):
                        index = int((int(q) - q) * 8 - 1)
                        bar += vbar_elements[index]
                    elif dx < int(q):
                        bar += " "
                    else:
                        bar += vbar_elements[-1]

                except IndexError:
                    bar += " "

            # assert len(bar) == tbox.w
            buf.add(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HBrailleChart(Tile):
    """Horizontal chart made with dots"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(buf, tbox)
        buf.add(self.text_color.pr(tbox.t))
        for dx in range(tbox.h):
            bar = ""
            for dy in range(tbox.w):
                dp_index = (dy - tbox.w) * 2
                try:
                    dp1 = self.datapoints[dp_index]
                    dp2 = self.datapoints[dp_index + 1]
                except IndexError:
                    # no data (yet)
                    bar += " "
                    continue

                q1 = (1 - dp1 / 100) * tbox.h
                q2 = (1 - dp2 / 100) * tbox.h
                if dx == int(q1):
                    index1 = int((q1 - int(q1)) * 4)
                    if dx == int(q2):  # both datapoints in the same rune
                        index2 = int((q2 - int(q2)) * 4)
                    else:
                        index2 = -1  # no dot
                    bar += _generate_braille(index1, index2)
                elif dx == int(q2):
                    # the right dot only is in the current rune
                    index2 = int((q2 - int(q2)) * 4)
                    bar += _generate_braille(-1, index2)
                else:
                    bar += " "

            buf.add(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HBrailleFilledChart(Tile):
    """Horizontal chart, filled with dots"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, buf: _Buf, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(buf, tbox)
        buf.add(self.text_color.pr(tbox.t))
        for dx in range(tbox.h):
            bar = ""
            for dy in range(tbox.w):
                dp_index = (dy - tbox.w) * 2
                try:
                    dp1 = self.datapoints[dp_index]
                    dp2 = self.datapoints[dp_index + 1]
                except IndexError:
                    # no data (yet)
                    bar += " "
                    continue

                q1 = (1 - dp1 / 100.0) * tbox.h
                q2 = (1 - dp2 / 100.0) * tbox.h
                if dx == int(q1):
                    index1 = 3 - int((q1 - int(q1)) * 4)
                elif dx > q1:
                    index1 = 3
                else:
                    index1 = 0
                if dx == int(q2):
                    index2 = 3 - int((q2 - int(q2)) * 4)
                elif dx > q2:
                    index2 = 3
                else:
                    index2 = 0
                bar += _generate_filled_braille(index1, index2)

            buf.add(tbox.t.move(tbox.x + dx, tbox.y), bar)


@contextlib.contextmanager
def open_terminal() -> Generator:
    """
    Helper function that creates a Blessed terminal session to restore the screen after
    the UI closes.
    """
    t = Terminal()

    with t.fullscreen(), t.hidden_cursor():
        yield t


def _pad(itr, n: int, fillvalue="") -> Generator:
    i = -1
    for i, value in enumerate(itr):
        yield i, value
    i += 1
    yield from enumerate(itertools.repeat(fillvalue, n - i), i)


def _generate_braille(le: int, ri: int) -> str:
    v = 0x28 * 256 + (braille_left[le] + braille_right[ri])
    return chr(v)


def _generate_filled_braille(lmax: int, rmax: int) -> str:
    v = 0x28 * 256
    for le in range(lmax):
        v += braille_r_left[le]
    for r in range(rmax):
        v += braille_r_right[r]
    return chr(v)
