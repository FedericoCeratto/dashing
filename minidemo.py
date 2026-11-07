#!/usr/bin/env python3

"""
    Small demo
"""

import math
import sys
import time

from dashing import (
    RGB,
    HBrailleChart,
    HBrailleFilledChart,
    HChart,
    HGauge,
    HSplit,
    Log,
    Text,
    VGauge,
    VSplit,
)


def main() -> None:

    ticker_interval = 1.0 / int(sys.argv[1])
    anim_speed = float(sys.argv[3]) / 1000

    vsplit = VSplit(
        Text("Hello World,\nthis is dashing."),
        Log(title="logs", color_high=RGB(0, 0, 0), color_low=RGB(200, 200, 200)),
        HChart(),
        HBrailleChart(),  # FIXME
    )
    vgauge2 = VGauge(val=5)
    braille_filled = HBrailleFilledChart()
    ui = HSplit(
        VSplit(
            HGauge(val=50, title="gauge", color_low="*A000FF", color_high="*A00000"),
            HGauge(label="label", color_low="*A0F09F", color_high="*D0FFFF"),
            # VChart(),  # FIXME
            HSplit(
                VGauge(val=0),
                vgauge2,
                VGauge(),
            ),
        ),
        vsplit,
        title="Dashing",
        color_high="*00F0F0",
        color_low="*50F0F0",
    )
    log: Log = ui.items[1].items[1]
    hchart = ui.items[1].items[-2]
    bchart = ui.items[1].items[-1]
    log.append("0 Hello world")

    ui.items[0].items.append(braille_filled)

    last_tick = time.monotonic()

    rad = 0.0
    cnt = 0
    while rad < math.pi * int(sys.argv[2]):
        amp = math.sin(rad)
        # You can access the tiles by index in the tile tree
        ui.items[0].items[0].value = int(50 + 49.9 * amp * math.sin(rad * 2))
        ui.items[0].items[1].value = int(50 + 45 * amp * math.sin(rad * 4))

        vgauges = ui.items[0].items[-1].items
        for gaugenum, vg in enumerate(vgauges):
            vg.value = 50 + 49.9 * amp * math.sin(rad * 4 + gaugenum)
            if vg.value > 90:
                vg.set_color("border_color", "#FF0000")
            else:
                vg.set_color("border_color", "#00FF00")

        # if rad % math.pi < 0.1:
        log.append(f"Processing... {int(rad * 100)}")

        hchart.append(50 + 50 * amp * math.sin(rad * 16))
        bchart.append(50 + 50 * amp * math.sin(rad * 8 + math.pi))
        braille_filled.append(50 + 50 * amp * math.sin(rad * 8 + math.pi))
        ui.display()

        # Increase rad and sleep
        rad += anim_speed
        time.sleep(max(0, last_tick + ticker_interval - time.monotonic()))
        last_tick = time.monotonic()


if __name__ == "__main__":
    main()
