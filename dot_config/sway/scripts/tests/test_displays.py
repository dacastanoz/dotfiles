import unittest

from tests.loader import load

d = load("displays")


def out(name, active=True, width=1920, height=1080, scale=1.0, make="M", model="X", serial="S", x=0, y=0, rate=60000):
    return {"name": name, "active": active, "scale": scale, "make": make, "model": model, "serial": serial,
            "rect": {"x": x, "y": y, "width": int(width / scale) if active else 0, "height": int(height / scale) if active else 0},
            "current_mode": {"width": width, "height": height, "refresh": rate} if active else None,
            "modes": [{"width": width, "height": height, "refresh": rate}]}


class Roles(unittest.TestCase):
    def test_internal_and_external(self):
        self.assertEqual(d.roles([out("HDMI-A-1"), out("eDP-1")]), ("eDP-1", "HDMI-A-1"))

    def test_no_external(self):
        self.assertEqual(d.roles([out("eDP-1")]), ("eDP-1", None))


class Layouts(unittest.TestCase):
    def test_extend_right_positions_external_at_logical_width(self):
        cmds = d.layout_commands("extend-right", "eDP-1", "HDMI-A-1", int_w=1536, ext_w=3072)
        self.assertIn("output eDP-1 enable position 0 0", cmds)
        self.assertIn("output HDMI-A-1 enable position 1536 0", cmds)

    def test_extend_left(self):
        cmds = d.layout_commands("extend-left", "eDP-1", "HDMI-A-1", int_w=1536, ext_w=3072)
        self.assertIn("output HDMI-A-1 enable position 0 0", cmds)
        self.assertIn("output eDP-1 enable position 3072 0", cmds)

    def test_external_only_enables_before_disabling(self):
        cmds = d.layout_commands("external", "eDP-1", "HDMI-A-1", int_w=1536, ext_w=3072)
        self.assertEqual(cmds, ["output HDMI-A-1 enable", "output eDP-1 disable"])

    def test_laptop_only(self):
        cmds = d.layout_commands("laptop", "eDP-1", "HDMI-A-1", int_w=1536, ext_w=3072)
        self.assertEqual(cmds, ["output eDP-1 enable", "output HDMI-A-1 disable"])

    def test_laptop_without_external(self):
        self.assertEqual(d.layout_commands("laptop", "eDP-1", None, 1536, 0), ["output eDP-1 enable"])


class Cycle(unittest.TestCase):
    def test_order_matches_the_old_toggle(self):
        self.assertEqual(d.next_layout("laptop"), "extend-right")
        self.assertEqual(d.next_layout("extend-right"), "mirror")
        self.assertEqual(d.next_layout("mirror"), "external")
        self.assertEqual(d.next_layout("external"), "laptop")

    def test_current_layout(self):
        both = [out("eDP-1"), out("HDMI-A-1")]
        self.assertEqual(d.current_layout(both, mirroring=False), "extend-right")
        self.assertEqual(d.current_layout(both, mirroring=True), "mirror")
        self.assertEqual(d.current_layout([out("eDP-1"), out("HDMI-A-1", active=False)], False), "laptop")
        self.assertEqual(d.current_layout([out("eDP-1", active=False), out("HDMI-A-1")], False), "external")


class CurrentProfile(unittest.TestCase):
    def test_reads_the_profile_name(self):
        self.assertEqual(d.parse_kanshi_status("Current profile: desk-benq\n"), "desk-benq")

    def test_no_profile_gives_none(self):
        self.assertIsNone(d.parse_kanshi_status("Couldn't connect to kanshi\n"))
        self.assertIsNone(d.parse_kanshi_status(""))


class Labels(unittest.TestCase):
    def test_messages_match_the_old_toggle(self):
        self.assertEqual(d.LAYOUT_LABELS["extend-right"], "Extended \u2192 right")
        self.assertEqual(d.LAYOUT_LABELS["external"], "TV only")
        self.assertEqual(d.LAYOUT_LABELS["laptop"], "Laptop only")
        self.assertIn("Mirror", d.LAYOUT_LABELS["mirror"])


class Kanshi(unittest.TestCase):
    def test_profile_is_keyed_by_identity_and_keeps_geometry(self):
        text = d.render_profile("desk", [
            out("eDP-1", scale=1.25, make="BOE", model="P1", serial="1"),
            out("HDMI-A-1", width=3840, height=2160, scale=1.5, make="BNQ", model="EW", serial="9", x=1536),
            out("DP-1", active=False, make="A", model="B", serial="C"),
        ])
        self.assertIn("profile desk {", text)
        self.assertIn('output "BOE P1 1" enable mode 1920x1080@60.000Hz position 0,0 scale 1.25', text)
        self.assertIn('output "BNQ EW 9" enable mode 3840x2160@60.000Hz position 1536,0 scale 1.5', text)
        self.assertIn('output "A B C" disable', text)

    def test_profile_names_are_sanitised(self):
        self.assertEqual(d.safe_name("my desk/../x!"), "mydesk..x")

    def test_profile_names_from_config(self):
        cfg = "# c\nprofile laptop {\n output eDP-1 enable\n}\nprofile docked {\n}\n"
        self.assertEqual(d.profile_names(cfg), ["laptop", "docked"])


if __name__ == "__main__":
    unittest.main()
