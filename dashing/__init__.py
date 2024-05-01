"""
Dashing allows to quickly create terminal-based dashboards in Python.

It focuses on practicality over completeness. If you want to have complete control
over every character on the screen, use ncurses or similar.

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
    - :class:`ColorRangeVGauge` - vertical gauge with coloring
    - :class:`VChart` - vertical chart
    - :class:`HChart` - horizontal chart
    - :class:`HBrailleChart`
    - :class:`HBrailleFilledChart`

All tiles accept ``title``, ``color``, ``border_color`` keywords arguments at init time.

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

__version__ = "0.2.0"

import colorsys
import contextlib
from collections import namedtuple, deque
import itertools
from typing import Literal, Optional, Tuple, Generator, List

from blessed import Terminal

# "graphic" elements

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

TBox = namedtuple("TBox", "t x y w h")
Color = Literal[0, 1, 2, 3, 4, 5, 6, 7]  # legacy


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
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return cls(int(r * 255), int(g * 255), int(b * 255))

    def to_hls(self) -> Tuple[float, float, float]:
        """Convert to HLS"""
        return colorsys.rgb_to_hls(self.r, self.g, self.b)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.r, self.g, self.b) == (other.r, other.g, other.b)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def pr(self, term) -> str:
        """Returns a printable string element"""
        return term.color_rgb(self.r, self.g, self.b)


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
        return RGB(0, 255, 0)  # FIXME

    return RGB(*rgb)


class Theme:
    """Color theming. Supports inheritance across UI elements and can be updated over time."""

    __slots__ = ["border", "text", "chart_high", "chart_low", "chart_gradient"]

    def __init__(
        self,
        border=RGB(0, 128, 0),  # FIXME
        text=RGB(128, 128, 128),
        chart_high=RGB.parse("*808080"),
        chart_low=RGB.parse("*808000"),
        chart_gradient="",
    ):
        self.border = border
        self.text = text
        self.chart_high = chart_high
        self.chart_low = chart_low
        self.chart_gradient = chart_gradient

    def interpolate_chart(self, steps: int, pos) -> RGB:
        """Interpolate between 2 colors. Used to generate gradients."""
        start = self.chart_high.to_hls()
        end = self.chart_low.to_hls()

        if steps <= 1:
            return RGB(255, 0, 0)  # FIXME

        # Interpolate HSL components
        h = start[0] + (end[0] - start[0]) * pos / (steps - 1)
        s = start[1] + (end[1] - start[1]) * pos / (steps - 1)
        el = start[2] + (end[2] - start[2]) * pos / (steps - 1)

        r, g, b = colorsys.hls_to_rgb(h, s, el)
        return RGB(int(r * 255), int(g * 255), int(b * 255))


# # Tiles # #


class Tile(object):
    """Base class for all Dashing tiles."""

    def __init__(
        self,
        title: str = "",
        border_color: Optional[Color] = None,
        color: Color = 0,
        theme: Optional[Theme] = None,
    ) -> None:
        """
        :param title: Title of the tile
        :param border_color: Color of the border. Setting this will enable a border and shrinks available size by 1
          character on each side.
        :param color: Color of the text inside the tile.
        """
        self.title = title
        self.color = color
        self.border_color = border_color
        self._terminal: Optional[Terminal] = None
        self.theme = theme
        self.parent: Optional[Tile] = None
        self.items: List[Tile] = []

    def _display(self, tbox: TBox) -> None:
        """
        Implement this method when subclassing :class:`.Tile`, to fill in the available space outlined by
        the ``tbox`` with the tile content.
        """
        raise NotImplementedError

    def _draw_borders_and_title(self, tbox: TBox):
        """
        Draw borders and title as needed and returns
        inset (x, y, width, height)
        """
        assert self.theme
        if self.border_color is not None:
            print(self.theme.border.pr(tbox.t))
            # left and right
            for dx in range(1, tbox.h - 1):
                print(tbox.t.move(tbox.x + dx, tbox.y) + border_v)
                print(tbox.t.move(tbox.x + dx, tbox.y + tbox.w - 1) + border_v)
            # bottom
            print(
                tbox.t.move(tbox.x + tbox.h - 1, tbox.y)
                + border_bl
                + border_h * (tbox.w - 2)
                + border_br
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
            print(tbox.t.move(tbox.x, tbox.y) + border_tl + border_t + border_tr)
        elif self.title:
            # top title without border
            margin = int((tbox.w - len(self.title)) / 20)

            title = (
                " " * margin + self.title + " " * (tbox.w - margin - len(self.title))
            )
            print(tbox.t.move(tbox.x, tbox.y) + title)

        if self.border_color is not None:
            return TBox(tbox.t, tbox.x + 1, tbox.y + 1, tbox.w - 2, tbox.h - 2)

        elif self.title:
            return TBox(tbox.t, tbox.x + 1, tbox.y, tbox.w - 1, tbox.h - 1)

        return TBox(tbox.t, tbox.x, tbox.y, tbox.w, tbox.h)

    def _fill_area(self, tbox: TBox, char: str) -> None:
        """Fill area with a character"""
        for dx in range(0, tbox.h):
            print(tbox.t.move(tbox.x + dx, tbox.y) + char * tbox.w)

    def display(self, terminal: Optional[Terminal] = None) -> None:
        """Render current tile and its items. Recurse into nested splits
        if any.
        """
        if self._terminal is None:
            t = self._terminal = terminal or Terminal()
        else:
            t = self._terminal

        tbox = TBox(t, 0, 0, t.width, t.height - 1)
        # self._fill_area(tbox, 0, 0, t.width, t.height - 1, "f")  # FIXME
        tbox = TBox(t, 0, 0, t.width, t.height - 1)
        self._display(tbox)
        # park cursor in a safe place and reset color
        print(t.move(t.height - 3, 0) + t.color(0))


class Split(Tile):
    """Split a box vertically (VSplit) or horizontally (HSplit)

    Splits create a hierarchy of UI elements
    """

    def __init__(self, *items: Tile, **kw) -> None:
        super().__init__(**kw)
        self.items: List[Tile] = list(items)
        self.update_children()

    def update_children(self) -> None:
        """Pass down the theming to children tiles and set the `parent` attribute"""
        for i in self.items:
            if i.theme is None:
                i.theme = self.theme
                i.parent = self

    def _display(self, tbox: TBox) -> None:
        """Render current tile and its items. Recurse into nested splits"""
        # apply default theme on root element
        if self.theme is None and self.parent is None:
            # I'm the root tile
            self.theme = Theme()  # FIXME

        tbox = self._draw_borders_and_title(tbox)

        if not self.items:
            # empty split
            # self._fill_area(tbox, " ")
            return

        if isinstance(self, VSplit):
            item_height = tbox.h // len(self.items)
            item_width = tbox.w
        else:
            item_height = tbox.h
            item_width = tbox.w // len(self.items)

        x = tbox.x
        y = tbox.y
        for i in self.items:
            # Apply theming to nested items on first run
            if i.theme is None:
                i.theme = self.theme

            i._display(TBox(tbox.t, x, y, item_width, item_height))
            if isinstance(self, VSplit):
                x += item_height
            else:
                y += item_width

        # Fill leftover area
        # if isinstance(self, VSplit):
        #     leftover_x = tbox.h - x + 1
        #     if leftover_x > 0:
        #         self._fill_area(TBox(tbox.t, x, y, tbox.w - 3, leftover_x), "Y")

        if isinstance(self, HSplit):
            leftover_y = tbox.w - y + 1
            if leftover_y > 0:
                self._fill_area(TBox(tbox.t, x, y, leftover_y - 1, tbox.h), " ")


class VSplit(Split):
    pass


class HSplit(Split):
    pass


class Text(Tile):
    """
    A multi-line text box. Example::

       Text('Hello World, this is dashing.', border_color=2),

    """

    def __init__(self, text: str, color: Color = 0, **kw) -> None:
        super().__init__(**kw)
        self.text: str = text
        self.color = color

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        for dx, line in pad(self.text.splitlines()[-(tbox.h) :], tbox.h):
            print(
                self.theme.text.pr(tbox.t)
                + tbox.t.move(tbox.x + dx, tbox.y)
                + line
                + " " * (tbox.w - len(line))
            )


class Log(Tile):
    """A log pane that scrolls automatically.
    Add new lines with :meth:`append`
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.logs: deque = deque(maxlen=50)

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        n_logs = len(self.logs)
        log_range = min(n_logs, tbox.h)
        start = n_logs - log_range

        h = 0.5
        s = 0.8
        v = 0.8
        # print(tbox.t.color(self.color))
        for dx, line in pad((self.logs[ln] for ln in range(start, n_logs)), tbox.h):
            # FIXME
            v = float(dx) / tbox.h
            # col = color(tbox.t, hsv=(h, s, v))
            print(self.theme.text.pr(tbox.t))
            print(tbox.t.move(tbox.x + dx, tbox.y) + line + " " * (tbox.w - len(line)))

    def append(self, msg: str) -> None:
        """Append a new log message at the bottom"""
        self.logs.append(msg)


class ColorGradientLog(Tile):
    """A log pane that scrolls automatically.
    Add new lines with :meth:`append`
    """


class HGauge(Tile):
    """Horizontal gauge"""

    def __init__(
        self, label: str = "", val=100, color: Color = 2, style: str = "", **kw
    ) -> None:
        super().__init__(color=color, **kw)
        self.value = val
        self.label = label
        sty = style.strip().split()
        self.color_start, self.color_end, self.color_style = sty[:3] + [None] * (
            3 - len(sty)
        )

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        # Compute colored bar width as float
        label_wid = len(self.label or "")
        if self.label:
            bar_wid = (tbox.w - label_wid - 3) * self.value / 100
            v_center = int((tbox.h) * 0.5)
        else:
            bar_wid = tbox.w * self.value / 100.0
            v_center = None
        bar_iwid = int(bar_wid)
        # Fill the colored part
        bar = ""
        for pos in range(bar_iwid):
            col = self.theme.interpolate_chart(bar_iwid, pos).pr(tbox.t)
            bar += col + hbar_elements[-1]

        # Pick the char for the partially-filled element
        selector = int((bar_wid - int(bar_wid)) * 7)
        bar += hbar_elements[selector]

        # Fill the remaining part with thin lines
        filler_wid = tbox.w - bar_iwid - 1
        if self.label:
            filler_wid -= label_wid + 1
        bar += hbar_elements[0] * filler_wid

        # draw bar
        # print(tbox.t.move(tbox.x, tbox.y + 1))
        for dx in range(0, tbox.h):
            m = tbox.t.move(tbox.x + dx, tbox.y)
            if self.label:
                if dx == v_center:
                    # draw label
                    print(m + self.label + " " + bar)
                else:
                    print(m + " " * label_wid + " " + bar)
            else:
                print(m + bar)


class VGauge(Tile):
    """Vertical gauge"""

    def __init__(self, val=100, color: Color = 2, **kw) -> None:
        super().__init__(color=color, **kw)
        self.value = val

    def _display(self, tbox: TBox) -> None:
        """Render current tile"""
        tbox = self._draw_borders_and_title(tbox)
        nh = tbox.h * (self.value / 100.5)
        print(tbox.t.move(tbox.x, tbox.y) + self.theme.text.pr(tbox.t))
        for dx in range(tbox.h):
            m = tbox.t.move(tbox.x + tbox.h - dx - 1, tbox.y)
            if dx < int(nh):
                bar = vbar_elements[-1] * tbox.w
            elif dx == int(nh):
                index = int((nh - int(nh)) * 8)
                bar = vbar_elements[index] * tbox.w
            else:
                bar = " " * tbox.w

            print(m + bar)


class ColorRangeVGauge(Tile):
    """Vertical gauge with color map.
    E.g.: green gauge for values below 50, red otherwise:
    colormap=((50, 2), (100, 1))
    """

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        nh = tbox.h * (self.value / 100.5)
        filled_element = vbar_elements[-1]
        col = 0
        # FIXME
        for thresh, col in self.colormap:
            if thresh > self.value:
                break
        print(tbox.t.move(tbox.x, tbox.y) + tbox.t.color(col))
        for dx in range(tbox.h):
            m = tbox.t.move(tbox.x + tbox.h - dx - 1, tbox.y)
            if dx < int(nh):
                bar = filled_element * tbox.w
            elif dx == int(nh):
                index = int((nh - int(nh)) * 8)
                bar = vbar_elements[index] * tbox.w
            else:
                bar = " " * tbox.w

            print(m + bar)


class ColorGradientVGauge(Tile):
    """Vertical gauge with color gradient."""

    def __init__(self, val=100, gradient="TODO", **kw):
        # TODO: configurable gradients
        super().__init__(**kw)
        self.value = val

    def _display(self, tbox: TBox):
        tbox = self._draw_borders_and_title(tbox)
        nh = tbox.h * (self.value / 100.5)
        filled_element = vbar_elements[-1]

        # TODO: configurable gradients
        out = [tbox.t.move(tbox.x, tbox.y)]
        h = (1 - self.value / 100) / 3
        for dx in range(tbox.h):
            p = 0.3
            v = p * (float(dx) / tbox.h) + (1 - p)
            h = 0.2
            s = 0.8
            col = self.theme.chart_high.pr(tbox.t)
            out.append(col)
            m = tbox.t.move(tbox.x + tbox.h - dx - 1, tbox.y)
            if dx < int(nh):
                bar = filled_element * tbox.w
            elif dx == int(nh):
                index = int((nh - int(nh)) * 8)
                bar = vbar_elements[index] * tbox.w
            else:
                bar = " " * tbox.w

            out.append(m + bar)
        print("".join(out))


class VChart(Tile):
    """Vertical chart. Values must be between 0 and 100 and can be float."""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=50)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        filled_element = hbar_elements[-1]
        scale = tbox.w / 100.0
        print(self.theme.text.pr(tbox.t))
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
            print(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HChart(Tile):
    """Horizontal chart, filled"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        print(self.theme.text.pr(tbox.t))
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
            print(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HBrailleChart(Tile):
    """Horizontal chart made with dots"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        print(self.theme.text.pr(tbox.t))
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
                    bar += generate_braille(index1, index2)
                elif dx == int(q2):
                    # the right dot only is in the current rune
                    index2 = int((q2 - int(q2)) * 4)
                    bar += generate_braille(-1, index2)
                else:
                    bar += " "

            print(tbox.t.move(tbox.x + dx, tbox.y) + bar)


class HBrailleFilledChart(Tile):
    """Horizontal chart, filled with dots"""

    def __init__(self, val=100, **kw) -> None:
        super().__init__(**kw)
        self.value = val
        self.datapoints: deque = deque(maxlen=500)

    def append(self, dp: float) -> None:
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox) -> None:
        tbox = self._draw_borders_and_title(tbox)
        print(self.theme.text.pr(tbox.t))
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
                bar += generate_filled_braille(index1, index2)

            print(tbox.t.move(tbox.x + dx, tbox.y) + bar)


@contextlib.contextmanager
def open_terminal() -> Generator:
    """
    Helper function that creates a Blessed terminal session to restore the screen after
    the UI closes.
    """
    t = Terminal()

    with t.fullscreen(), t.hidden_cursor():
        yield t


def pad(itr, n: int, fillvalue="") -> Generator:
    i = -1
    for i, value in enumerate(itr):
        yield i, value
    i += 1
    yield from enumerate(itertools.repeat(fillvalue, n - i), i)


def generate_braille(le: int, ri: int) -> str:
    v = 0x28 * 256 + (braille_left[le] + braille_right[ri])
    return chr(v)


def generate_filled_braille(lmax: int, rmax: int) -> str:
    v = 0x28 * 256
    for le in range(lmax):
        v += braille_r_left[le]
    for r in range(rmax):
        v += braille_r_right[r]
    return chr(v)
