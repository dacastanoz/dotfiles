import json
import unittest

from tests.loader import load

pf = load("pango-filter")


class Convert(unittest.TestCase):
    def test_color_tags(self):
        self.assertEqual(pf.convert("%{F#88c0d0}X%{F-} 42"), '<span color="#88c0d0">X</span> 42')

    def test_plain_text_is_escaped(self):
        self.assertEqual(pf.convert("a & b <c>"), "a &amp; b &lt;c&gt;")

    def test_empty_stays_empty_so_the_module_hides(self):
        self.assertEqual(pf.convert(""), "")

    def test_unclosed_color_is_closed(self):
        self.assertEqual(pf.convert("%{F#fff}X"), '<span color="#fff">X</span>')

    def test_stray_close_is_dropped(self):
        self.assertEqual(pf.convert("X%{F-}"), "X")

    def test_new_color_closes_the_previous_one(self):
        self.assertEqual(pf.convert("%{F#111}a%{F#222}b%{F-}"),
                         '<span color="#111">a</span><span color="#222">b</span>')

    def test_other_polybar_tags_are_removed(self):
        self.assertEqual(pf.convert("%{A1:cmd:}x%{A}%{B#000}y%{B-}"), "xy")


class JsonMode(unittest.TestCase):
    def test_json_lines_pass_through_untouched(self):
        line = '{"text":"<span color=\\"#fff\\">x</span> a &amp; b","tooltip":"t","class":"ok"}'
        self.assertEqual(pf.convert_json(line), line)

    def test_plain_lines_are_wrapped_as_json(self):
        out = json.loads(pf.convert_json("%{F#bf616a}!%{F-} a & b"))
        self.assertEqual(out["text"], '<span color="#bf616a">!</span> a &amp; b')
        self.assertEqual(out["class"], "error")

    def test_bad_json_is_wrapped_not_passed(self):
        out = json.loads(pf.convert_json('{"text": oops'))
        self.assertEqual(out["class"], "error")


if __name__ == "__main__":
    unittest.main()
