# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import unittest
from unittest import mock

from ddm import controller as C
from ddm import ddc


class FakeMonitor(C.Controller):
    """A controller whose DDC reads come from attributes instead of I2C."""

    def __init__(self, left=0x19, right=0x0F, layout=0x24, this=0x0F,
                 usb_here=True, width=2560, connector="card1-DP-1"):
        super().__init__()
        self.monitor = ddc.Monitor(connector, "DELL U4025QW", "", [13], 13)
        self.left, self.right, self.layout = left, right, layout
        self.cfg["this_input"] = this
        self.cfg["inputs"] = [0x0F, 0x11, 0x19]
        self.cfg["layouts"] = [lay.code for lay in C.LAYOUTS]
        self._usb = usb_here
        self.width = width
        self.usb_moves = []

    def get_input(self): return self.left
    def get_right_input(self): return self.right
    def get_pxp(self): return self.layout
    def usb_here(self): return self._usb
    def get_usb(self): return 0xBC00
    def _current_width(self): return self.width

    def set_usb(self, here, wait=6.0):
        self.usb_moves.append(here)
        self._usb = here
        return "moved"


class Layouts(unittest.TestCase):
    def test_find_by_key_name_and_code(self):
        self.assertEqual(C.find_layout("75-25").code, 0x2A)
        self.assertEqual(C.find_layout("75/25").code, 0x2A)
        self.assertEqual(C.find_layout("Wide Left").code, 0x2A)
        self.assertEqual(C.find_layout("0x21").key, "pip-small")
        self.assertIsNone(C.find_layout("bogus"))

    def test_codes_are_unique(self):
        self.assertEqual(len({lay.code for lay in C.LAYOUTS}), len(C.LAYOUTS))


class ConnectorInputs(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(C._connector_inputs("card0-HDMI-A-1"), C.HDMI_INPUTS)
        self.assertEqual(C._connector_inputs("card1-DP-1"),
                         C.DP_INPUTS | C.USBC_INPUTS)
        self.assertIsNone(C._connector_inputs("card0-Writeback-1"))


class Detect(unittest.TestCase):
    def detect(self, tb_possible, **kw):
        ctl = FakeMonitor(**kw)
        with mock.patch.object(C, "_usb_c_video_possible",
                               return_value=tb_possible):
            return ctl.detect_this_input()[0]

    def test_dp_without_thunderbolt_link(self):
        # The case that used to report the Mac: Ubuntu on the right.
        self.assertEqual(self.detect(False), 0x0F)

    def test_even_split_is_ambiguous(self):
        self.assertIsNone(self.detect(True))

    def test_narrow_side_in_uneven_split(self):
        self.assertEqual(self.detect(True, layout=0x2A, width=1280), 0x0F)

    def test_wide_side_in_uneven_split(self):
        self.assertEqual(self.detect(True, layout=0x2A, width=3840), 0x19)

    def test_hdmi_connector(self):
        self.assertEqual(self.detect(True, connector="card0-HDMI-A-1"), 0x11)


class Cross(unittest.TestCase):
    def test_edge_next_to_other_computer_moves_keyboard(self):
        ctl = FakeMonitor()                          # Mac left, Ubuntu right
        self.assertIsNotNone(ctl.cross("left"))
        self.assertEqual(ctl.usb_moves, [False])

    def test_outer_edge_does_nothing(self):
        ctl = FakeMonitor()
        self.assertIsNone(ctl.cross("right"))
        self.assertEqual(ctl.usb_moves, [])

    def test_follows_swapped_sides(self):
        ctl = FakeMonitor(left=0x0F, right=0x19)     # Ubuntu left
        self.assertIsNone(ctl.cross("left"))
        self.assertIsNotNone(ctl.cross("right"))

    def test_only_in_side_by_side(self):
        for layout in (0x00, 0x21):                  # single, inset
            ctl = FakeMonitor(layout=layout)
            self.assertIsNone(ctl.cross("left"))

    def test_keyboard_already_away(self):
        ctl = FakeMonitor(usb_here=False)
        self.assertIsNone(ctl.cross("left"))


class Switch(unittest.TestCase):
    def test_side_by_side_moves_keyboard(self):
        ctl = FakeMonitor(usb_here=True)
        ctl.switch()
        self.assertEqual(ctl.usb_moves, [False])

    def test_single_view_flips_input(self):
        ctl = FakeMonitor(left=0x0F, layout=0x00)
        ctl.cfg["other_input"] = 0x19
        with mock.patch.object(ctl, "set_input") as set_input:
            ctl.switch()
        set_input.assert_called_once_with(0x19)

    def test_single_view_needs_both_inputs(self):
        ctl = FakeMonitor(layout=0x00)
        ctl.cfg["other_input"] = None
        with self.assertRaises(ddc.DDCError):
            ctl.switch()


class Levels(unittest.TestCase):
    def setUp(self):
        self.ctl = FakeMonitor()
        self.written = []
        p1 = mock.patch.object(ddc, "getvcp",
                               return_value=ddc.VCPValue(0x10, [75, 100]))
        p2 = mock.patch.object(ddc, "setvcp", side_effect=lambda bus, code, v:
                               self.written.append((code, v)))
        p1.start(), p2.start()
        self.addCleanup(mock.patch.stopall)

    def test_absolute_and_relative(self):
        self.assertEqual(self.ctl.adjust_level("brightness", "60"), 60)
        self.assertEqual(self.ctl.adjust_level("brightness", "+10"), 85)
        self.assertEqual(self.ctl.adjust_level("brightness", "-20"), 55)
        self.assertEqual(self.written[0], (0x10, 60))

    def test_clamped_to_range(self):
        self.assertEqual(self.ctl.adjust_level("volume", "+50"), 100)
        self.assertEqual(self.ctl.adjust_level("volume", "-500"), 0)

    def test_not_a_number(self):
        with self.assertRaises(ValueError):
            self.ctl.adjust_level("contrast", "lots")


class Config(unittest.TestCase):
    def test_round_trip_keeps_hex_codes_and_defaults(self):
        cfg = C.load_config()
        cfg["this_input"] = 0x0F
        cfg["vcp"]["usb"] = 0xE7
        C.save_config(cfg)
        with open(C.CONFIG_FILE) as f:
            self.assertEqual(json.load(f)["vcp"]["usb"], "0xE7")
        again = C.load_config()
        self.assertEqual(again["this_input"], 0x0F)
        self.assertEqual(again["vcp"]["usb"], 0xE7)
        self.assertEqual(again["vcp"]["brightness"], 0x10)

    def test_config_lives_in_test_directory(self):
        self.assertTrue(C.CONFIG_FILE.startswith(os.environ["XDG_CONFIG_HOME"]))


if __name__ == "__main__":
    unittest.main()
