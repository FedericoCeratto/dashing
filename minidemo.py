#!/usr/bin/env python3

"""
    Small demo
"""

import time
import sys
import math

from dashing import (
    HSplit,
    VSplit,
    HGauge,
    VGauge,
    ColorRangeVGauge,
    ColorGradientVGauge,
    Text,
    Log,
    HChart,
    HBrailleChart,
    RGB,
)


def main() -> None:

    ticker_interval = 1.0 / int(sys.argv[1])

    ui = HSplit(
        VSplit(
            HGauge(val=50, title="gauge", border_color=5),
            HGauge(label="label", val=20, border_color=5),
            HSplit(
                VGauge(val=0, border_color=2),
                VGauge(val=5, border_color=2),
                # ColorRangeVGauge(
                ColorGradientVGauge(
                    val=100,
                    border_color=2,
                ),
            ),
        ),
        VSplit(
            Text("Hello World,\nthis is dashing.", border_color=2),
            Log(title="logs", border_color=5),
            HChart(border_color=2, color=2),
            HBrailleChart(border_color=2, color=2),
        ),
        title="Dashing",
    )
    log = ui.items[1].items[1]
    hchart = ui.items[1].items[-2]
    bchart = ui.items[1].items[-1]
    log.append("0 -----")
    log.append("1 Hello")
    log.append("2 World")

    last_tick = time.monotonic()

    rad = 0.0
    cnt = 0
    while rad < math.pi:
        amp = math.sin(rad)
        ui.items[0].items[0].value = int(50 + 49.9 * amp * math.sin(rad * 2))
        ui.items[0].items[1].value = int(50 + 45 * amp * math.sin(rad * 4))
        ui.items[0].items[2].value = int(50 + 45 * amp * math.sin(rad + 1))

        vgauges = ui.items[0].items[-1].items
        for gaugenum, vg in enumerate(vgauges):
            vg.value = 50 + 49.9 * amp * math.sin(rad * 4 + gaugenum)

        if rad % math.pi < 0.1:
            log.append("Processing... %d" % (len(log.logs) - 2))

        hchart.append(50 + 50 * amp * math.sin(rad * 16))
        bchart.append(50 + 50 * amp * math.sin(rad * 8 + math.pi))
        ui.display()

        ui.theme.border = RGB.from_hsv(amp, 0.5, 0.5)
        ui.theme.chart_high = RGB.from_hsv(amp, 0.5, 0.5)

        # Increase rad and sleep
        rad += 0.003
        time.sleep(max(0, last_tick + ticker_interval - time.monotonic()))
        last_tick = time.monotonic()


if __name__ == "__main__":
    main()
