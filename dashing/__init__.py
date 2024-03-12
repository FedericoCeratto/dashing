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
__init__ and _display. See dashing.py for examples.

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

    ui = HSplit(
            VSplit(
                HGauge(val=50, title="foo", border_color=5),
            )
        )
    # access a tile by index
    gauge = ui.items[0].items[0]
    gauge.value = 3.0

    # display/refresh the ui
    ui.display()
"""

__version__ = "0.1.0"

from .dashing import *  # noqa: F401, F403
