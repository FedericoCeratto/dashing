#!/usr/bin/env python3
"""
Small demo
"""

import math
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
    VChart,
    VGauge,
    VSplit,
    open_terminal,
)

# Colors can be "#RRGGBB" (RGB), "*HHSSVV" (HSV) or RGB(r, g, b)
GREEN = "#00ff00"
MAGENTA = "#ff00ff"


def wave(cycle: int, speed: float, phase: float) -> float:
    return 50.0 + 50.0 * math.sin(cycle / 200.0 * speed + phase)


def main() -> None:
    ui = HSplit(
        VSplit(
            HGauge(val=50, title="only title", border_color=MAGENTA, color_low="*A000FF", color_high="*A00000"),  # hg1
            HGauge(label="only label", color_low="*A0F09F", color_high="*D0FFFF"),  # hg2
            HGauge(val=20, border=False),  # hg3 (no label, no border)
            HGauge(label="label, no border", val=55, border=False),  # hg4
            HSplit(
                VGauge(border_color=GREEN),
                VGauge(border_color=GREEN, color_low="#0000ff", color_high="#00ffff"),
                VGauge(border_color=GREEN, color_low="#ffff00", color_high="#ff8000"),
                # gradient from green (low values) to red (high values)
                VGauge(val=100, border_color=GREEN, color_low=GREEN, color_high="#ff0000"),
            ),
        ),
        VSplit(
            Text("Hello World,\nthis is dashing.", border_color=GREEN),
            Log(title="logs", color_high=RGB(0, 0, 0), color_low=RGB(200, 200, 200)),
            VChart(border_color=GREEN, color=GREEN),
            HChart(border_color=GREEN, color=GREEN),
            HBrailleChart(border_color=GREEN, color=GREEN),
            HBrailleFilledChart(border_color=GREEN, color=GREEN),
        ),
        title="Dashing",
    )
    log = ui.items[1].items[1]
    vchart = ui.items[1].items[2]
    hchart = ui.items[1].items[3]
    bchart = ui.items[1].items[4]
    bfchart = ui.items[1].items[5]
    log.append("0 -----")
    log.append("1 Hello")
    log.append("2 -----")
    prev_time = time.time()

    last_tick = time.monotonic()

    with open_terminal() as terminal:
        for cycle in range(0, 100_000):
            # horizontal gauges on top left
            hgauges = ui.items[0].items
            for gaugenum, hg in enumerate(hgauges):
                hg.value = wave(cycle, speed=2, phase=gaugenum)

            # vertical gauges on bottom left
            vgauges = ui.items[0].items[-1].items
            for gaugenum, vg in enumerate(vgauges):
                vg.value = wave(cycle, speed=2, phase=gaugenum)
                pass

            t = int(time.time())
            if t != prev_time:
                log.append("%s" % t)
                prev_time = t
            vchart.append(wave(cycle, 2, 0))
            hchart.append(wave(cycle, 2, 1))
            bchart.append(wave(cycle, 2, 2))
            bfchart.append(wave(cycle, 2, 3))
            ui.display(terminal)

            time.sleep(max(0, last_tick + 1 / 60.0 - time.monotonic()))
            last_tick = time.monotonic()


if __name__ == "__main__":
    main()
