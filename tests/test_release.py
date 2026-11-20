# SPDX-License-Identifier: GPL-3.0-or-later
"""Things that must agree with each other in a release."""

import json
import os
import re
import unittest

import mullion

ROOT = os.path.dirname(os.path.dirname(__file__))
EXT = os.path.join(ROOT, "extension", "mullion@ivoks.github.io")


class Release(unittest.TestCase):
    def test_version_matches_debian_changelog(self):
        with open(os.path.join(ROOT, "debian", "changelog")) as f:
            first = f.readline()
        version = re.match(r"\S+ \(([^)-]+)", first).group(1)
        self.assertEqual(version, mullion.__version__)

    def test_man_page_version(self):
        with open(os.path.join(ROOT, "data", "mullion.1")) as f:
            self.assertIn(f'"mullion {mullion.__version__}"', f.readline())

    def test_extension_uuid_and_gettext_domain(self):
        with open(os.path.join(EXT, "metadata.json")) as f:
            meta = json.load(f)
        from mullion import extension, i18n
        self.assertEqual(meta["uuid"], extension.UUID)
        self.assertEqual(os.path.basename(EXT), extension.UUID)
        self.assertEqual(meta["gettext-domain"], i18n.DOMAIN)

    def test_app_id_is_consistent(self):
        # Read it from the source: importing mullion.gui needs GTK, which
        # the build environment doesn't have.
        with open(os.path.join(ROOT, "mullion", "gui.py")) as f:
            app_id = re.search(r'^APP_ID = "([^"]+)"', f.read(), re.M).group(1)
        names = os.listdir(os.path.join(ROOT, "data"))
        self.assertIn(app_id + ".desktop.in", names)
        with open(os.path.join(EXT, "quickmenu.js")) as f:
            self.assertIn(f"'{app_id}'", f.read())


if __name__ == "__main__":
    unittest.main()
