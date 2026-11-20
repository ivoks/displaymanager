# SPDX-License-Identifier: GPL-3.0-or-later
"""Check every translation keeps the {placeholders} of its original, so a
.format() call can never fail at runtime in another language."""

import glob
import os
import re
import unittest

PO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "po")


def entries(path):
    """Yield (msgid, msgstr, fuzzy) from a .po file."""
    text = open(path, encoding="utf-8").read()
    for block in text.split("\n\n"):
        m = re.search(r'^msgid ((?:".*"\n?)+)^msgstr ((?:".*"\n?)+)', block, re.M)
        if not m:
            continue
        join = lambda s: "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', s))
        yield join(m.group(1)), join(m.group(2)), "#, fuzzy" in block


def placeholders(s):
    return sorted(re.findall(r"\{(\w*)\}", s))


class Translations(unittest.TestCase):
    def test_po_files_exist_for_linguas(self):
        with open(os.path.join(PO_DIR, "LINGUAS")) as f:
            langs = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for lang in langs:
            self.assertTrue(os.path.exists(os.path.join(PO_DIR, lang + ".po")), lang)

    def test_placeholders_match(self):
        for path in glob.glob(os.path.join(PO_DIR, "*.po")):
            for msgid, msgstr, fuzzy in entries(path):
                if not msgid or not msgstr or fuzzy:
                    continue
                with self.subTest(po=os.path.basename(path), msgid=msgid):
                    self.assertEqual(placeholders(msgid), placeholders(msgstr))


if __name__ == "__main__":
    unittest.main()
