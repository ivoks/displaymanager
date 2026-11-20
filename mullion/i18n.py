# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ante Karamatic
"""gettext setup.

Translations live in po/*.po and are compiled to
<localedir>/<lang>/LC_MESSAGES/mullion.mo by `make`.  When running
from a source checkout the compiled files in build/locale are used;
otherwise the system locale directory (e.g. /usr/share/locale).
"""

from __future__ import annotations

import gettext
import locale
import os

DOMAIN = "mullion"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCE_LOCALEDIR = os.path.join(_ROOT, "build", "locale")


def _localedir() -> str | None:
    env = os.environ.get("MULLION_LOCALEDIR")
    if env:
        return env
    if os.path.isdir(_SOURCE_LOCALEDIR):
        return _SOURCE_LOCALEDIR
    # Installed as <prefix>/share/mullion: use <prefix>/share/locale,
    # which also covers installs outside /usr (e.g. PREFIX=~/.local).
    installed = os.path.join(os.path.dirname(_ROOT), "locale")
    if os.path.isdir(installed):
        return installed
    return None                     # gettext's default


try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

_translation = gettext.translation(DOMAIN, localedir=_localedir(),
                                   fallback=True)

_ = _translation.gettext


def N_(message: str) -> str:
    """Mark a string for extraction without translating it yet."""
    return message
