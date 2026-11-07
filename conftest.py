import os

import pytest


@pytest.fixture(autouse=True)
def skip_if_windows():
    if os.name == "nt":
        pytest.exit("Test suite not supported on Windows. Please use WSL.")
    else:
        yield
