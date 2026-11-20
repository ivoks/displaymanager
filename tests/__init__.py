# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests.  They never touch real hardware or the user's settings:
config goes to a temporary directory and output is in English."""

import os
import tempfile

os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="displaymanager-test-")
os.environ["LANGUAGE"] = "C"
os.environ["DISPLAYMANAGER_LOCALEDIR"] = "/nonexistent"
os.environ.setdefault("GSETTINGS_BACKEND", "memory")
