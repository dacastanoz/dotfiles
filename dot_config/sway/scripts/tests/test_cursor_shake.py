import struct
import unittest

from tests.loader import load

cs = load("cursor-shake")
EV_KEY, EV_ABS, EV_REL = 1, 3, 2


def feed(det, events):
    return [det.feed(*e) for e in events]


def shake(start=0.0, legs=8, leg_time=0.09, leg_travel=300, steps=5):
    """Fast horizontal strokes, alternating direction."""
    out, t, sign = [], start, 1
    for _ in range(legs):
        for _ in range(steps):
            t += leg_time / steps
            out.append((t, sign * leg_travel / steps, 0))
        sign = -sign
    return out


class Detector(unittest.TestCase):
    def test_fast_shake_fires(self):
        self.assertTrue(any(feed(cs.ShakeDetector(), shake())))

    def test_straight_line_does_not_fire(self):
        events = [(i * 0.01, 60, 0) for i in range(200)]
        self.assertFalse(any(feed(cs.ShakeDetector(), events)))

    def test_slow_back_and_forth_does_not_fire(self):
        self.assertFalse(any(feed(cs.ShakeDetector(), shake(legs=12, leg_time=0.6))))

    def test_small_jitter_does_not_fire(self):
        self.assertFalse(any(feed(cs.ShakeDetector(), shake(legs=30, leg_time=0.03, leg_travel=10, steps=2))))

    def test_vertical_shake_does_not_fire(self):
        events = [(t, 0, dx) for t, dx, _ in shake()]
        self.assertFalse(any(feed(cs.ShakeDetector(), events)))

    def test_diagonal_mostly_vertical_shake_does_not_fire(self):
        events = [(t, dx * 0.3, dx * 2) for t, dx, _ in shake()]
        self.assertFalse(any(feed(cs.ShakeDetector(), events)))

    def test_noise_inside_a_stroke_is_not_a_reversal(self):
        events = []
        t = 0.0
        for i in range(100):
            t += 0.01
            events.append((t, -3 if i % 5 == 0 else 40, 0))
        self.assertFalse(any(feed(cs.ShakeDetector(), events)))

    def test_pause_resets_progress(self):
        det = cs.ShakeDetector()
        feed(det, shake(legs=cs.MIN_REVERSALS))  # one short of firing, then a long pause
        self.assertFalse(any(feed(det, shake(start=5.0, legs=cs.MIN_REVERSALS))))

    def test_keeps_firing_while_shaking_continues(self):
        results = feed(cs.ShakeDetector(), shake(legs=20))
        first = results.index(True)
        self.assertGreater(sum(results[first:]), 20)


class Controller(unittest.TestCase):
    def setUp(self):
        self.sizes = []
        self.ctl = cs.CursorController(self.sizes.append, normal=24, large=72, hold=1.0)

    def test_fire_enlarges_once(self):
        self.ctl.on_shake(0.0)
        self.ctl.on_shake(0.1)
        self.assertEqual(self.sizes, [72])

    def test_reverts_after_idle(self):
        self.ctl.on_shake(0.0)
        self.ctl.tick(0.5)
        self.assertEqual(self.sizes, [72])
        self.ctl.tick(1.01)
        self.assertEqual(self.sizes, [72, 24])

    def test_shaking_extends_the_hold(self):
        self.ctl.on_shake(0.0)
        self.ctl.on_shake(0.9)
        self.ctl.tick(1.5)
        self.assertEqual(self.sizes, [72])
        self.ctl.tick(2.0)
        self.assertEqual(self.sizes, [72, 24])

    def test_close_reverts_only_when_enlarged(self):
        self.ctl.close()
        self.assertEqual(self.sizes, [])
        self.ctl.on_shake(0.0)
        self.ctl.close()
        self.assertEqual(self.sizes, [72, 24])

    def test_can_enlarge_again_after_revert(self):
        self.ctl.on_shake(0.0)
        self.ctl.tick(2.0)
        self.ctl.on_shake(3.0)
        self.assertEqual(self.sizes, [72, 24, 72])


class Touchpad(unittest.TestCase):
    def setUp(self):
        self.tp = cs.TouchpadTracker(res_x=30, res_y=30)

    def test_no_delta_on_first_contact_then_mm_scaled_deltas(self):
        self.tp.finger(True)
        self.tp.abs_x(1000)
        self.tp.abs_y(500)
        self.assertIsNone(self.tp.sync())
        self.tp.abs_x(1030)
        dx, dy = self.tp.sync()
        self.assertAlmostEqual(dx, 1 * cs.TOUCHPAD_UNITS_PER_MM)
        self.assertEqual(dy, 0)

    def test_lifting_resets_so_no_jump_on_next_touch(self):
        self.tp.finger(True)
        self.tp.abs_x(1000)
        self.tp.sync()
        self.tp.finger(False)
        self.assertIsNone(self.tp.sync())
        self.tp.finger(True)
        self.tp.abs_x(3000)
        self.assertIsNone(self.tp.sync())

    def test_no_events_without_finger(self):
        self.tp.abs_x(1000)
        self.tp.abs_x(2000)
        self.assertIsNone(self.tp.sync())

    def test_multitouch_gestures_are_ignored(self):
        self.tp.finger(True)
        self.tp.abs_x(1000)
        self.tp.sync()
        self.tp.multi(True)
        self.tp.abs_x(1500)
        self.assertIsNone(self.tp.sync())


def bitmap(*bits):
    """Render bit numbers in the sysfs format: hex 64-bit words, most significant first."""
    words = {}
    for b in bits:
        words[b // 64] = words.get(b // 64, 0) | (1 << (b % 64))
    top = max(words) if words else 0
    return " ".join(format(words.get(i, 0), "x") for i in range(top, -1, -1))


class Classify(unittest.TestCase):
    def caps(self, rel=(), abs_=(), key=(), ev=()):
        return dict(ev=bitmap(*ev), rel=bitmap(*rel), abs=bitmap(*abs_), key=bitmap(*key))

    def test_bitmap_parser(self):
        self.assertEqual(cs.parse_bitmap("1 0"), {64})
        self.assertEqual(cs.parse_bitmap("a"), {1, 3})

    def test_mouse(self):
        c = self.caps(ev=(EV_KEY, EV_REL), rel=(cs.REL_X, cs.REL_Y), key=(cs.BTN_LEFT,))
        self.assertEqual(cs.classify_caps(**c), "mouse")

    def test_touchpad(self):
        c = self.caps(ev=(EV_KEY, EV_ABS), abs_=(cs.ABS_X, cs.ABS_Y), key=(cs.BTN_TOOL_FINGER,))
        self.assertEqual(cs.classify_caps(**c), "touchpad")

    def test_keyboard_is_rejected(self):
        c = self.caps(ev=(EV_KEY,), key=(30, 31, 32))
        self.assertIsNone(cs.classify_caps(**c))

    def test_combined_device_with_letter_keys_is_rejected(self):
        c = self.caps(ev=(EV_KEY, EV_REL), rel=(cs.REL_X, cs.REL_Y), key=(cs.BTN_LEFT, 30))
        self.assertIsNone(cs.classify_caps(**c))

    def test_touchscreen_without_tool_finger_is_rejected(self):
        c = self.caps(ev=(EV_KEY, EV_ABS), abs_=(cs.ABS_X, cs.ABS_Y), key=(330,))
        self.assertIsNone(cs.classify_caps(**c))


def xcursor_bytes(*sizes):
    head = b"Xcur" + struct.pack("<III", 16, 0x10000, len(sizes))
    toc = b"".join(struct.pack("<III", 0xFFFD0002, size, 0) for size in sizes)
    return head + toc


class CursorSizes(unittest.TestCase):
    def test_reads_sizes_from_an_xcursor_file(self):
        self.assertEqual(cs.xcursor_sizes(xcursor_bytes(24, 48, 48, 72)), {24, 48, 72})

    def test_rejects_non_xcursor_data(self):
        self.assertEqual(cs.xcursor_sizes(b"not a cursor"), set())

    def test_pick_largest_real_size_not_above_request(self):
        self.assertEqual(cs.pick_large_size({24, 30, 36, 48, 72}, 96), 72)
        self.assertEqual(cs.pick_large_size({24, 96, 128}, 96), 96)

    def test_falls_back_to_request_when_sizes_unknown(self):
        self.assertEqual(cs.pick_large_size(set(), 96), 96)


if __name__ == "__main__":
    unittest.main()
