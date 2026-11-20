# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import io
import json
import unittest
from unittest import mock

from mullion import cli, ddc
from tests.test_controller import FakeMonitor


def run(argv, ctl):
    out = io.StringIO()
    with mock.patch.object(cli, "Controller", return_value=ctl), \
            mock.patch.object(FakeMonitor, "connect", return_value=ctl.monitor), \
            contextlib.redirect_stdout(out):
        rc = cli.main(argv)
    return rc, out.getvalue()


class State(unittest.TestCase):
    """`state` feeds the GNOME Quick Settings menu."""

    def test_side_by_side(self):
        ctl = FakeMonitor(layout=0x2A, usb_here=False)
        ctl.cfg["layouts"] = [0x00, 0x24, 0x2A]
        rc, out = run(["state"], ctl)
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
        rc, out = run(["state"], ctl)
        self.assertFalse(json.loads(out)["multi"])

    def test_error_is_json_too(self):
        ctl = FakeMonitor()
        with mock.patch.object(FakeMonitor, "get_input",
                               side_effect=ddc.DDCError("no monitor")):
            rc, out = run(["state"], ctl)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out), {"error": "no monitor"})


class CrossCheck(unittest.TestCase):
    """`cross <edge> --check` tells the extension whether to offer the
    pop-up, without switching anything."""

    def test_other_computer_on_that_side(self):
        ctl = FakeMonitor()
        ctl.cfg["input_labels"] = {"0x19": "Mac"}
        rc, out = run(["cross", "left", "--check"], ctl)
        self.assertEqual((rc, out.strip()), (0, "Mac"))
        self.assertEqual(ctl.usb_moves, [])

    def test_nothing_on_that_side(self):
        rc, out = run(["cross", "right", "--check"], FakeMonitor())
        self.assertEqual((rc, out), (1, ""))


class Arguments(unittest.TestCase):
    def test_bad_input_code_is_an_error_not_a_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            cli.main(["input", "zz"])
        self.assertEqual(e.exception.code, 2)
        self.assertIn("zz", err.getvalue())

    def test_second_input(self):
        ctl = FakeMonitor()
        with mock.patch.object(ctl, "set_second_input") as set_second:
            rc, _out = run(["-q", "second", "0x19"], ctl)
        self.assertEqual(rc, 0)
        set_second.assert_called_once_with(0x19)


if __name__ == "__main__":
    unittest.main()
