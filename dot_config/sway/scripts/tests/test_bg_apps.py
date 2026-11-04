import json
import os
import signal
import unittest

from tests.loader import load

bg = load("bg-apps")
UID = 1000
NOW = 10_000.0


def proc(pid, ppid=1, name="app", uid=UID, tty=0, start=NOW - 100, rss=1024, argv=None, state="S", cgroup=""):
    return bg.Proc(pid=pid, ppid=ppid, uid=uid, comm=name, argv=argv if argv is not None else [name],
                   tty=tty, start=start, rss_kb=rss, state=state, cgroup=cgroup)


def names(listed):
    return sorted(p.pid for p in listed)


class Classification(unittest.TestCase):
    def classify(self, procs, windows=()):
        return bg.classify(procs, set(windows), UID, NOW)

    def test_windowless_app_is_listed(self):
        self.assertEqual(names(self.classify([proc(10)])), [10])

    def test_app_with_window_is_not_listed(self):
        self.assertEqual(self.classify([proc(10)], windows=[10]), [])

    def test_other_users_are_never_listed(self):
        self.assertEqual(self.classify([proc(10, uid=0)]), [])

    def test_helper_children_collapse_to_the_top_level_app(self):
        procs = [proc(10, name="electron"), proc(11, ppid=10, name="electron"), proc(12, ppid=11, name="electron")]
        self.assertEqual(names(self.classify(procs)), [10])

    def test_descendant_with_window_hides_the_ancestor(self):
        procs = [proc(10, name="launcher"), proc(11, ppid=10, name="gui")]
        self.assertEqual(self.classify(procs, windows=[11]), [])

    def test_ancestor_with_window_hides_the_descendant(self):
        procs = [proc(10, name="ghostty"), proc(11, ppid=10, name="fish"), proc(12, ppid=11, name="sleepy")]
        self.assertEqual(self.classify(procs, windows=[10]), [])

    def test_infrastructure_is_filtered_with_its_children(self):
        procs = [proc(10, name="waybar"), proc(11, ppid=10, name="temperature.sh"), proc(12, name="pipewire")]
        self.assertEqual(self.classify(procs), [])

    def test_children_of_session_roots_are_candidates(self):
        procs = [proc(5, name="sway"), proc(10, ppid=5, name="forgotten")]
        self.assertEqual(names(self.classify(procs)), [10])

    def test_shell_wrapper_is_skipped_in_favour_of_its_child(self):
        procs = [proc(10, name="sh"), proc(11, ppid=10, name="forgotten")]
        self.assertEqual(names(self.classify(procs)), [11])

    def test_zombies_and_kernel_threads_are_ignored(self):
        procs = [proc(10, state="Z"), proc(11, argv=[])]
        self.assertEqual(self.classify(procs), [])

    def test_very_young_processes_are_ignored(self):
        self.assertEqual(self.classify([proc(10, start=NOW - 1)]), [])


class ObservedInRealSway(unittest.TestCase):
    """False positives seen on the first run in a real session."""

    def classify(self, procs, windows=()):
        return bg.classify(procs, set(windows), UID, NOW)

    def test_clipboard_holder_and_tray_helper_are_infrastructure(self):
        self.assertEqual(self.classify([proc(10, name="wl-copy"), proc(11, name="blueman-tray")]), [])

    def test_infrastructure_shell_script_hides_its_children(self):
        procs = [proc(10, name="bash", argv=["bash", "/home/d/.config/sway/scripts/session-env"]),
                 proc(11, ppid=10, name="swaymsg")]
        self.assertEqual(self.classify(procs), [])

    def test_osd_pipe_reader_is_infrastructure(self):
        self.assertEqual(self.classify([proc(10, name="tail", argv=["tail", "-f", "/run/user/1000/wob.pipe"])]), [])

    def test_autostart_watcher_hides_its_journal_reader(self):
        procs = [proc(10, name="limine-snapper-", argv=["/usr/bin/limine-snapper-notify"]),
                 proc(11, ppid=10, name="journalctl")]
        self.assertEqual(self.classify(procs), [])

    def test_ssh_session_is_a_root_not_an_app(self):
        procs = [proc(10, name="sshd-session"), proc(11, ppid=10, name="forgotten")]
        self.assertEqual(names(self.classify(procs)), [11])

    def test_user_systemd_service_is_infrastructure(self):
        cg = "/user.slice/user-1000.slice/user@1000.service/app.slice/rclone-unidad.service"
        self.assertEqual(self.classify([proc(10, name="rclone", cgroup=cg)]), [])

    def test_app_scope_started_through_systemd_is_still_an_app(self):
        cg = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-foo-123.scope"
        self.assertEqual(names(self.classify([proc(10, cgroup=cg)])), [10])

    def test_app_service_template_is_still_an_app(self):
        cg = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-com.foo.bar@x.service"
        self.assertEqual(names(self.classify([proc(10, cgroup=cg)])), [10])

    def test_app_in_the_login_session_scope_is_an_app(self):
        cg = "/user.slice/user-1000.slice/session-c1.scope"
        self.assertEqual(names(self.classify([proc(10, cgroup=cg)])), [10])


class ClaudeRule(unittest.TestCase):
    def classify(self, procs, windows=()):
        return bg.classify(procs, set(windows), UID, NOW)

    def test_claude_without_tty_or_window_is_listed_even_as_a_child_of_a_listed_app(self):
        procs = [proc(10, name="tmux"), proc(11, ppid=10, name="claude")]
        self.assertEqual(names(self.classify(procs)), [10, 11])

    def test_claude_without_tty_is_listed_even_under_infrastructure(self):
        procs = [proc(10, name="waybar"), proc(11, ppid=10, name="claude")]
        self.assertEqual(names(self.classify(procs)), [11])

    def test_claude_with_tty_under_infrastructure_stays_filtered(self):
        procs = [proc(10, name="waybar"), proc(11, ppid=10, name="claude", tty=34816)]
        self.assertEqual(self.classify(procs), [])

    def test_claude_with_a_window_relation_is_not_listed(self):
        procs = [proc(10, name="ghostty"), proc(11, ppid=10, name="claude")]
        self.assertEqual(self.classify(procs, windows=[10]), [])

    def test_versioned_binary_is_recognised_by_argv0(self):
        p = proc(11, name="2.1.314", argv=["claude", "--resume"])
        self.assertTrue(bg.is_claude(p))

    def test_node_launched_claude_code_is_recognised(self):
        p = proc(11, name="node", argv=["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"])
        self.assertTrue(bg.is_claude(p))

    def test_desktop_app_is_not_the_cli(self):
        p = proc(11, name="claude-desktop", argv=["/usr/lib/claude-desktop/claude-desktop"])
        self.assertFalse(bg.is_claude(p))


class Display(unittest.TestCase):
    def test_display_name_prefers_the_script_for_interpreters(self):
        p = proc(10, name="python3", argv=["/usr/bin/python3", "/home/d/tool.py", "--x"])
        self.assertEqual(bg.display_name(p), "tool.py")

    def test_display_name_uses_argv0_basename(self):
        p = proc(10, name="2.1.314", argv=["/home/d/.local/bin/claude"])
        self.assertEqual(bg.display_name(p), "claude")

    def test_age_formatting(self):
        self.assertEqual(bg.format_age(59), "59s")
        self.assertEqual(bg.format_age(61), "1m")
        self.assertEqual(bg.format_age(3700), "1h 1m")
        self.assertEqual(bg.format_age(90000), "1d 1h")

    def test_memory_formatting(self):
        self.assertEqual(bg.format_mem(512), "512 KiB")
        self.assertEqual(bg.format_mem(2048), "2 MiB")
        self.assertEqual(bg.format_mem(3 * 1024 * 1024), "3.0 GiB")


class WaybarOutput(unittest.TestCase):
    def test_empty_list_gives_empty_text_so_the_module_hides(self):
        out = json.loads(bg.waybar_json([], NOW))
        self.assertEqual(out["text"], "")
        self.assertEqual(out["count"], 0)

    def test_tooltip_has_name_pid_age_memory(self):
        out = json.loads(bg.waybar_json([proc(42, name="forgotten", rss=2048, start=NOW - 61)], NOW))
        self.assertEqual(out["count"], 1)
        self.assertIn("1", out["text"])
        for piece in ("forgotten", "42", "1m", "2 MiB"):
            self.assertIn(piece, out["tooltip"])

    def test_tooltip_escapes_markup(self):
        out = json.loads(bg.waybar_json([proc(42, argv=["a<b&c"], name="x")], NOW))
        self.assertIn("a&lt;b&amp;c", out["tooltip"])


class Tree(unittest.TestCase):
    def test_window_pids_walks_tiling_and_floating_nodes(self):
        tree = {"pid": 1, "type": "root", "nodes": [
            {"type": "output", "nodes": [{"type": "workspace", "nodes": [
                {"type": "con", "pid": 10, "nodes": []}],
                "floating_nodes": [{"type": "floating_con", "pid": 20, "nodes": []}]}]}],
            "floating_nodes": []}
        self.assertEqual(bg.window_pids(tree), {10, 20})

    def test_compositor_root_pid_is_not_a_window(self):
        self.assertEqual(bg.window_pids({"type": "root", "pid": 7, "nodes": [], "floating_nodes": []}), set())


class Terminate(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.owner = {42: UID}
        self.starts = {42: 500.0}

    def term(self, pid, start=500.0):
        return bg.terminate(pid, start, UID, owner_of=self.owner.get, start_of=self.starts.get,
                            send=lambda p, s: self.sent.append((p, s)))

    def test_sends_sigterm_only(self):
        self.assertTrue(self.term(42))
        self.assertEqual(self.sent, [(42, signal.SIGTERM)])

    def test_refuses_foreign_pid(self):
        self.owner[42] = 0
        self.assertFalse(self.term(42))
        self.assertEqual(self.sent, [])

    def test_refuses_vanished_pid(self):
        del self.owner[42]
        self.assertFalse(self.term(42))
        self.assertEqual(self.sent, [])

    def test_refuses_reused_pid(self):
        self.assertFalse(self.term(42, start=499.0))
        self.assertEqual(self.sent, [])

    def test_module_never_references_sigkill(self):
        with open(bg.__file__) as fh:
            self.assertNotIn("SIGKILL", fh.read())


class ProcParsing(unittest.TestCase):
    def test_parse_stat_handles_spaces_and_parens_in_comm(self):
        line = "42 (a b) c) S 7 42 42 34816 42 0 0 0 0 0 0 0 0 0 20 0 1 0 12345 0 0"
        parsed = bg.parse_stat(line)
        self.assertEqual(parsed["comm"], "a b) c")
        self.assertEqual(parsed["state"], "S")
        self.assertEqual(parsed["ppid"], 7)
        self.assertEqual(parsed["tty"], 34816)
        self.assertEqual(parsed["starttime"], 12345)


if __name__ == "__main__":
    unittest.main()
