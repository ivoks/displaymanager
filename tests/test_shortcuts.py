# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from ddm import shortcuts as S


class Accelerators(unittest.TestCase):
    def test_modifier_order_and_aliases_do_not_matter(self):
        self.assertEqual(S.normalize("<Super><Alt>8"), S.normalize("<Alt><Super>8"))
        self.assertEqual(S.normalize("<Primary><Super>k"),
                         S.normalize("<Super><Control>K"))
        self.assertNotEqual(S.normalize("<Super><Alt>8"),
                            S.normalize("<Super><Alt>9"))
        self.assertIsNone(S.normalize("<Super>"))

    def test_label(self):
        self.assertEqual(S.label("<Alt><Super>9"), "Super+Alt+9")
        self.assertEqual(S.label("<Super><Control>k"), "Super+Ctrl+K")

    def test_keypad_twin(self):
        self.assertEqual(S.keypad_twin("<Super><Alt>2"), "<Super><Alt>KP_2")
        self.assertIsNone(S.keypad_twin("<Super><Control>k"))
        self.assertIsNone(S.keypad_twin(None))


class Defaults(unittest.TestCase):
    def test_every_layout_has_a_shortcut(self):
        self.assertEqual(len(S.LAYOUT_ACTIONS), len(S.LAYOUTS))

    def test_defaults_are_unique(self):
        keys = [S.normalize(a[2]) for a in S.ACTIONS.values()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_defaults_avoid_known_gnome_bindings(self):
        # Super+Ctrl+digit: GNOME Shell dock apps; Super+Alt+8: magnifier.
        taken = {S.normalize(f"<Super><Control>{i}") for i in range(10)}
        taken.add(S.normalize("<Super><Alt>8"))
        for action, (_t, _c, accel) in S.ACTIONS.items():
            self.assertNotIn(S.normalize(accel), taken, action)

    def test_names(self):
        self.assertEqual(S.gnome_name("usb"), "Monitor: Move keyboard & mouse")
        self.assertEqual(S.gnome_name("layout-75-25"),
                         "Monitor: Wide Left layout")


if __name__ == "__main__":
    unittest.main()
