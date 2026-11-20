# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests.  They never touch real hardware or the user's settings:
config goes to a temporary directory and output is in English."""

import os
import tempfile

os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="mullion-test-")
os.environ["LANGUAGE"] = "C"
os.environ["MULLION_LOCALEDIR"] = "/nonexistent"
os.environ.setdefault("GSETTINGS_BACKEND", "memory")


# No test may run the real ddcutil: fail loudly if one tries.
from mullion import ddc as _ddc  # noqa: E402


def _no_hardware(args, timeout=15):
    raise AssertionError(f"test tried to run ddcutil {' '.join(args)}")


_ddc._run = _no_hardware
