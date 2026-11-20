# SPDX-License-Identifier: GPL-3.0-or-later
import os
import unittest
from unittest import mock

from ddm import ddc

DATA = os.path.join(os.path.dirname(__file__), "data")


def run_returning(text):
    return mock.patch.object(ddc, "_run", return_value=text)


class GetVCP(unittest.TestCase):
    def test_simple_non_continuous(self):
        with run_returning("VCP 60 SNC x19\n"):
            v = ddc.getvcp(13, 0x60)
        self.assertEqual(v.low, 0x19)

    def test_continuous_keeps_maximum(self):
        with run_returning("VCP 10 C 75 100\n"):
            v = ddc.getvcp(13, 0x10)
        self.assertEqual((v.value, v.maximum), (75, 100))

    def test_complex_non_continuous(self):
        with run_returning("VCP E8 CNC xff xff x00 x0f\n"):
            v = ddc.getvcp(13, 0xE8)
        self.assertEqual(v.value, 0x000F)
        self.assertEqual(v.low, 0x0F)
        self.assertEqual(v.raw, [0xFF, 0xFF, 0x00, 0x0F])

    def test_noise_before_result_is_ignored(self):
        out = ("Discarding cached sleep adjustment data for bus /dev/i2c-13. "
               "EDID has changed.\nVCP E9 CNC x00 xff x00 x24\n")
        with run_returning(out):
            self.assertEqual(ddc.getvcp(13, 0xE9).low, 0x24)

    def test_unsupported_feature_raises(self):
        with run_returning("VCP 8D ERR\n"):
            with self.assertRaises(ddc.DDCError):
                ddc.getvcp(13, 0x8D)

    def test_garbage_raises(self):
        with run_returning("nothing useful\n"):
            with self.assertRaises(ddc.DDCError):
                ddc.getvcp(13, 0x60)


class SetVCP(unittest.TestCase):
    def test_null_response_is_success(self):
        err = ddc.DDCError("Setting value failed, rc=DDCRC_NULL_RESPONSE(-3002)")
        with mock.patch.object(ddc, "_run", side_effect=err) as run:
            ddc.setvcp(13, 0xE7, 0xFF00)
        self.assertIn("--noverify", run.call_args.args[0])
        self.assertIn("0xff00", run.call_args.args[0])

    def test_other_errors_propagate(self):
        with mock.patch.object(ddc, "_run", side_effect=ddc.DDCError("boom")):
            with self.assertRaises(ddc.DDCError):
                ddc.setvcp(13, 0x10, 50)


class Capabilities(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(DATA, "capabilities-u4025qw.txt")) as f:
            text = f.read()
        with run_returning(text):
            self.caps = ddc.capabilities(13)

    def test_inputs(self):
        self.assertEqual(set(self.caps[0x60]), {0x0F, 0x11, 0x19})

    def test_layouts(self):
        self.assertEqual(set(self.caps[0xE9]),
                         {0x00, 0x01, 0x02, 0x21, 0x22, 0x24, 0x27, 0x28,
                          0x29, 0x2A})

    def test_inline_values(self):
        self.assertEqual(set(self.caps[0xE7]), {0x02, 0x03})

    def test_features_without_values(self):
        self.assertEqual(self.caps[0x10], {})


class Discovery(unittest.TestCase):
    def test_edid_descriptors(self):
        edid = bytearray(128)
        edid[54:72] = b"\0\0\0\xfc\0" + b"DELL U4025QW\n "
        edid[72:90] = b"\0\0\0\xff\0" + b"SERIAL123\n   "
        desc = ddc._edid_descriptors(bytes(edid))
        self.assertEqual(desc[0xFC], "DELL U4025QW")
        self.assertEqual(desc[0xFF], "SERIAL123")

    def test_probe_reports_access_error(self):
        mon = ddc.Monitor("card1-DP-1", "DELL", "", [13, 4])
        with mock.patch.object(ddc, "bus_accessible", return_value=False):
            with self.assertRaises(ddc.DDCAccessError):
                ddc.probe_bus(mon)

    def test_probe_picks_working_bus(self):
        mon = ddc.Monitor("card1-DP-1", "DELL", "", [13, 4])

        def getvcp(bus, code):
            if bus == 13:
                raise ddc.DDCError("no answer")
            return ddc.VCPValue(code, [0x0F])
        with mock.patch.object(ddc, "bus_accessible", return_value=True), \
                mock.patch.object(ddc, "getvcp", side_effect=getvcp):
            self.assertEqual(ddc.probe_bus(mon), 4)


if __name__ == "__main__":
    unittest.main()
