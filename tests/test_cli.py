# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import io
import json
import unittest
from unittest import mock

from ddm import cli, ddc
from tests.test_controller import FakeMonitor


def run(argv, ctl):
    out = io.StringIO()
    with mock.patch.object(cli, "Controller", return_value=ctl), \
            mock.patch.object(FakeMonitor, "connect", return_value=ctl.monitor), \
            contextlib.redirect_stdout(out):
        rc = cli.main(argv)
    return rc, out.getvalue()


class State(unittest.TestCase):
    """`state --json` feeds the GNOME Quick Settings menu."""

    def test_side_by_side(self):
        ctl = FakeMonitor(layout=0x2A, usb_here=False)
        ctl.cfg["layouts"] = [0x00, 0x24, 0x2A]
        rc, out = run(["state", "--json"], ctl)
        st = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(st["layout"], "75-25")
        self.assertEqual(st["layout_title"], "Wide Left")
        self.assertTrue(st["multi"])
        self.assertIs(st["usb_here"], False)
        self.assertEqual([l["key"] for l in st["layouts"]],
                         ["single", "50-50", "75-25"])
        self.assertEqual(st["model"], "DELL U4025QW")

    def test_single_is_not_multi(self):
        ctl = FakeMonitor(layout=0x00)
        rc, out = run(["state", "--json"], ctl)
        self.assertFalse(json.loads(out)["multi"])

    def test_error_is_json_too(self):
        ctl = FakeMonitor()
        with mock.patch.object(FakeMonitor, "get_input",
                               side_effect=ddc.DDCError("no monitor")):
            rc, out = run(["state", "--json"], ctl)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out), {"error": "no monitor"})


if __name__ == "__main__":
    unittest.main()
