"""
Dashing allows to quickly create terminal-based dashboards in Python.

It focuses on practicality over completeness. If you want to have complete control
over every character on the screen, use ncurses or similar.

Dashing automatically fills the screen with "tiles".

There are 2 type of "container" tiles that allow vertical and horizontal splitting
called VSplit and HSplit. Dashing scales them based on the screen size.

Any tile passed as argument at init time will be nested using the .items attribute

.items can be used to access, add or remove nested tiles.

You can easily extend Dashing with new tile types. Subclass :class:`Tile`, implement
__init__ and _display.

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

All tiles accept title, color, border_color keywords arguments at init time.

Gauges represent an instant value between 0 and 100.
You can set a value at init time using the val keyword argument or access the
.value attribute at any time.

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

__version__ = "0.1.0"

import contextlib
import itertools
from collections import deque, namedtuple
from enum import Enum
from typing import Literal, Optional, Tuple, Union

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


class Color(Enum):
    Black = 0
    Red = 1
    Green = 2
    Yellow = 3
    Blue = 4
    Magenta = 5
    Cyan = 6
    White = 7


ColorLiteral = Literal[0, 1, 2, 3, 4, 5, 6, 7]
ColorValue = Union[Color, ColorLiteral]
Colormap = Tuple[Tuple[float, ColorValue], ...]
TBox = namedtuple("TBox", "t x y w h")


class Tile:
    def __init__(
        self,
        title: str = None,
        border_color: ColorValue = None,
        color: ColorValue = Color.Black,
    ):
        self.title = title
        self.color = color
        self.border_color = border_color
        self._terminal: Optional[Terminal] = None

    def _display(self, tbox: TBox, parent: Optional["Tile"]):
        """Render current tile"""
        raise NotImplementedError

    def _draw_borders_and_title(self, tbox: TBox):
        """
        Draw borders and title as needed and returns
        inset (x, y, width, height)
        """
        if self.border_color is not None:
            print(tbox.t.color(self.border_color))
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
            if self.title is None:
                # top border without title
                border_t = border_h * (tbox.w - 2)
            else:
                # top border with title
                margin = int((tbox.w - len(self.title)) / 20)
                border_t = (
                    border_h * (margin - 1) + " " * margin + self.title + " " * margin
                )
                border_t += (tbox.w - len(border_t) - 2) * border_h
            # top
            print(tbox.t.move(tbox.x, tbox.y) + border_tl + border_t + border_tr)
        elif self.title is not None:
            # top title without border
            margin = int((tbox.w - len(self.title)) / 20)

            title = (
                " " * margin + self.title + " " * (tbox.w - margin - len(self.title))
            )
            print(tbox.t.move(tbox.x, tbox.y) + title)

        if self.border_color is not None:
            return TBox(tbox.t, tbox.x + 1, tbox.y + 1, tbox.w - 2, tbox.h - 2)

        elif self.title is not None:
            return TBox(tbox.t, tbox.x + 1, tbox.y, tbox.w - 1, tbox.h - 1)

        return TBox(tbox.t, tbox.x, tbox.y, tbox.w, tbox.h)

    def _fill_area(self, tbox: TBox, char: str, *a, **kw):  # FIXME
        """Fill area with a character"""
        # for dx in range(0, height):
        #    print(tbox.t.move(x + dx, tbox.y) + char * width)
        pass

    def display(self, terminal: Terminal = None):
        """Render current tile and its items. Recurse into nested splits
        if any.
        """
        if self._terminal is None:
            t = self._terminal = terminal or Terminal()
        else:
            t = self._terminal

        tbox = TBox(t, 0, 0, t.width, t.height - 1)
        self._fill_area(tbox, 0, 0, t.width, t.height - 1, "f")  # FIXME
        tbox = TBox(t, 0, 0, t.width, t.height - 1)
        self._display(tbox, None)
        # park cursor in a safe place and reset color
        print(t.move(t.height - 3, 0) + t.color(0))


class Split(Tile):
    """Split a box vertically (VSplit) or horizontally (HSplit)"""

    def __init__(self, *items: Tile, **kw):
        super().__init__(**kw)
        self.items = items

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        """Render current tile and its items. Recurse into nested splits"""
        tbox = self._draw_borders_and_title(tbox)

        if not self.items:
            # empty split
            self._fill_area(tbox, " ")
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
            i._display(TBox(tbox.t, x, y, item_width, item_height), self)
            if isinstance(self, VSplit):
                x += item_height
            else:
                y += item_width

        # Fill leftover area
        if isinstance(self, VSplit):
            leftover_x = tbox.h - x + 1
            if leftover_x > 0:
                self._fill_area(TBox(tbox.t, x, y, tbox.w, leftover_x), " ")
        else:
            leftover_y = tbox.w - y + 1
            if leftover_y > 0:
                self._fill_area(TBox(tbox.t, x, y, leftover_y, tbox.h), " ")


class VSplit(Split):
    pass


class HSplit(Split):
    pass


class Text(Tile):
    """
    A multi-line text box. Example::

       Text('Hello World, this is dashing.', border_color=2),

    """

    def __init__(self, text: str, color: ColorValue = Color.Black, **kw):
        super().__init__(**kw)
        self.text: str = text
        self.color = color

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        for dx, line in pad(self.text.splitlines()[-(tbox.h) :], tbox.h):
            print(
                tbox.t.color(self.color)
                + tbox.t.move(tbox.x + dx, tbox.y)
                + line
                + " " * (tbox.w - len(line))
            )


class Log(Tile):
    """A log pane that scrolls automatically.
    Add new lines with :meth:`append`
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.logs = deque(maxlen=50)

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        n_logs = len(self.logs)
        log_range = min(n_logs, tbox.h)
        start = n_logs - log_range
        print(tbox.t.color(self.color))
        for dx, line in pad((self.logs[ln] for ln in range(start, n_logs)), tbox.h):
            print(tbox.t.move(tbox.x + dx, tbox.y) + line + " " * (tbox.w - len(line)))

    def append(self, msg: str):
        """Append a new log message at the bottom"""
        self.logs.append(msg)


class HGauge(Tile):
    """Horizontal gauge"""

    def __init__(
        self, label: str = None, val=100, color: ColorValue = Color.Green, **kw
    ):
        super().__init__(color=color, **kw)
        self.value = val
        self.label = label

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        if self.label:
            wi = (tbox.w - len(self.label) - 3) * self.value / 100
            v_center = int((tbox.h) * 0.5)
        else:
            wi = tbox.w * self.value / 100.0
            v_center = None
        index = int((wi - int(wi)) * 7)
        bar = hbar_elements[-1] * int(wi) + hbar_elements[index]
        print(tbox.t.color(self.color) + tbox.t.move(tbox.x, tbox.y + 1))
        if self.label:
            n_pad = tbox.w - 1 - len(self.label) - len(bar)
        else:
            n_pad = tbox.w - len(bar)
        bar += hbar_elements[0] * n_pad
        # draw bar
        for dx in range(0, tbox.h):
            m = tbox.t.move(tbox.x + dx, tbox.y)
            if self.label:
                if dx == v_center:
                    # draw label
                    print(m + self.label + " " + bar)
                else:
                    print(m + " " * len(self.label) + " " + bar)
            else:
                print(m + bar)


class VGauge(Tile):
    """Vertical gauge"""

    def __init__(self, val=100, color: ColorValue = Color.Green, **kw):
        super().__init__(color=color, **kw)
        self.value = val

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        """Render current tile"""
        tbox = self._draw_borders_and_title(tbox)
        nh = tbox.h * (self.value / 100.5)
        print(tbox.t.move(tbox.x, tbox.y) + tbox.t.color(self.color))
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

    def __init__(self, val=100, colormap: Colormap = (), **kw):
        self.colormap = colormap
        super().__init__(**kw)
        self.value = val

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        nh = tbox.h * (self.value / 100.5)
        filled_element = vbar_elements[-1]
        col = 0
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


class VChart(Tile):
    """Vertical chart. Values must be between 0 and 100 and can be float."""

    def __init__(self, val=100, **kw):
        super().__init__(**kw)
        self.value = val
        self.datapoints = deque(maxlen=50)

    def append(self, dp: float):
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        filled_element = hbar_elements[-1]
        scale = tbox.w / 100.0
        print(tbox.t.color(self.color))
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

    def __init__(self, val=100, **kw):
        super().__init__(**kw)
        self.value = val
        self.datapoints = deque(maxlen=500)

    def append(self, dp: float):
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        print(tbox.t.color(self.color))
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

    def __init__(self, val=100, **kw):
        super().__init__(**kw)
        self.value = val
        self.datapoints = deque(maxlen=500)

    def append(self, dp: float):
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox: TBox, parent: Optional[Tile]):
        tbox = self._draw_borders_and_title(tbox)
        print(tbox.t.color(self.color))
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

    def __init__(self, val=100, **kw):
        super().__init__(**kw)
        self.value = val
        self.datapoints = deque(maxlen=500)

    def append(self, dp: float):
        """Append a new value: int or float between 1 and 100"""
        self.datapoints.append(dp)

    def _display(self, tbox, parent):
        tbox = self._draw_borders_and_title(tbox)
        print(tbox.t.color(self.color))
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
def open_terminal():
    """
    Helper function that creates a Blessed terminal session to restore the screen after
    the UI closes.
    """
    t = Terminal()
    with t.fullscreen(), t.hidden_cursor():
        yield t


def pad(itr, n, fillvalue=""):
    i = -1
    for i, value in enumerate(itr):
        yield i, value
    i += 1
    yield from enumerate(itertools.repeat(fillvalue, n - i), i)


def generate_braille(l: int, r: int):
    v = 0x28 * 256 + (braille_left[l] + braille_right[r])
    return chr(v)


def generate_filled_braille(lmax: int, rmax: int):
    v = 0x28 * 256
    for l in range(lmax):
        v += braille_r_left[l]
    for r in range(rmax):
        v += braille_r_right[r]
    return chr(v)
