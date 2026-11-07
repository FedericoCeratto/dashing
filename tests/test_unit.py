"""
    Basic unit tests
"""

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
