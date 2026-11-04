import json
import re
import time
import unittest

from tests.harness import Sandbox


class Bar(Sandbox):
    def all_ok(self, age=120):
        for r in self.REMOTES:
            self.old_status(r, last_ok=int(time.time()) - age)

    def test_healthy(self):
        self.all_ok()
        b = self.bar()
        self.assertIn("synced 2m ago", b["text"])
        self.assertEqual(b["class"], "ok")
        self.assertIn("alpha", b["tooltip"])

    def test_old_status_files_render(self):
        self.all_ok()
        self.assertTrue(self.bar()["text"])

    def test_never_synced(self):
        self.assertIn("no sync yet", self.bar()["text"])

    def test_stale_after_one_hour(self):
        self.all_ok(age=3700)
        b = self.bar()
        self.assertIn("no sync for 1h", b["text"])
        self.assertEqual(b["class"], "warning")

    def test_not_stale_before_one_hour(self):
        self.all_ok(age=3400)
        self.assertEqual(self.bar()["class"], "ok")

    def progress(self, **kv):
        d = self.tmp / "run/drive-sync"
        d.mkdir(parents=True, exist_ok=True)
        (d / "progress").write_text("".join(f"{k}={v}\n" for k, v in kv.items()))

    def hold_lock(self):
        import os, subprocess
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        holder = subprocess.Popen(["flock", str(lock), "sleep", "30"], env=self.env)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(0.3)

    def test_running_listing_never_shows_a_fraction(self):
        self.all_ok()
        self.hold_lock()
        self.progress(remote="alpha", index=1, total=3, mode="normal", phase="listing", percent="", bytes_done="",
                      bytes_total="", speed="", eta="", files_total=0, files_done=0, started=int(time.time()) - 72)
        b = self.bar()
        self.assertRegex(b["text"], r"alpha listing 1m1\ds")
        self.assertNotRegex(b["text"], r"\d/3")
        self.assertEqual(b["class"], "syncing")

    def test_running_transfer(self):
        self.all_ok()
        self.hold_lock()
        self.progress(remote="alpha", index=1, total=3, mode="normal", phase="copying", percent="45", bytes_done="1 GiB",
                      bytes_total="2 GiB", speed="1 MiB/s", eta="1m", files_total=30, files_done=12, started=int(time.time()) - 5)
        self.assertIn("alpha 45% 12/30", self.bar()["text"])

    def test_running_does_not_hide_critical(self):
        self.all_ok()
        self.write_status("beta", state="auth", message="x", streak=2, last_ok=int(time.time()))
        self.hold_lock()
        self.progress(remote="alpha", phase="listing", started=int(time.time()))
        b = self.bar()
        self.assertIn("alpha listing", b["text"])
        self.assertIn("1 problem", b["text"])

    def test_retry_time_shown_for_backoff(self):
        self.all_ok()
        at = int(time.time()) + 1200
        self.write_status("alpha", state="rate-limited", message="x", next_attempt=at, streak=1, last_ok=int(time.time()))
        b = self.bar()
        self.assertIn("alpha retry " + time.strftime("%H:%M", time.localtime(at)), b["text"])
        self.assertEqual(b["class"], "warning")

    def test_network_errors_warn_and_name_the_remote(self):
        self.all_ok()
        at = int(time.time()) + 1200
        self.write_status("beta", state="network", message="m", next_attempt=at, streak=3, last_ok=int(time.time()) - 60)
        b = self.bar()
        self.assertIn("beta retry " + time.strftime("%H:%M", time.localtime(at)), b["text"])
        self.assertEqual(b["class"], "warning")

    def critical(self, state, want, **kw):
        self.all_ok()
        self.write_status("gamma", state=state, message="m", last_ok=int(time.time()), **kw)
        b = self.bar()
        self.assertIn(want, b["text"])
        self.assertEqual(b["class"], "critical")

    def test_critical_states(self):
        for state, want, kw in [("needs-resync", "gamma resync", {}), ("auth", "gamma auth", {"streak": 2}),
                                ("too-many-deletes", "gamma deletes", {}), ("access-check", "gamma access", {}),
                                ("gdoc-edit", "gamma edit Doc", {}), ("delete-cap", "gamma 240 deletes", {"delete_count": 240}),
                                ("error", "gamma error", {"streak": 2}), ("hung", "gamma hung", {"streak": 2})]:
            with self.subTest(state):
                self.critical(state, want, **kw)

    def test_single_auth_is_only_a_warning(self):
        self.all_ok()
        self.write_status("alpha", state="auth", message="m", streak=1, last_ok=int(time.time()))
        self.assertEqual(self.bar()["class"], "warning")

    def test_battery_skip_not_failure_even_when_stale(self):
        for r in self.REMOTES:
            self.write_status(r, state="battery-skip", message="b", last_ok=int(time.time()) - 9000)
        b = self.bar()
        self.assertIn("battery", b["text"])
        self.assertEqual(b["class"], "battery")

    def test_all_offline(self):
        for r in self.REMOTES:
            self.write_status(r, state="offline", message="n", last_ok=int(time.time()) - 9000)
        b = self.bar()
        self.assertIn("offline", b["text"])
        self.assertEqual(b["class"], "offline")

    def test_one_offline_is_named(self):
        self.all_ok()
        self.write_status("beta", state="offline", message="n", last_ok=int(time.time()))
        self.assertIn("beta offline", self.bar()["text"])

    def test_critical_beats_offline_and_counts_more(self):
        self.write_status("alpha", state="needs-resync", message="m")
        self.write_status("beta", state="delete-cap", message="m", delete_count=9)
        self.write_status("gamma", state="offline", message="m")
        b = self.bar()
        self.assertEqual(b["class"], "critical")
        self.assertIn("+1", b["text"])

    def test_markup_is_escaped(self):
        self.all_ok()
        self.write_status("alpha", state="error", message="a <b> & c", streak=1, last_ok=int(time.time()))
        b = self.bar()
        self.assertIn("a &lt;b&gt; &amp; c", b["tooltip"])

    def test_tooltip_shared_client_names_rclone_remote_with_guide(self):
        self.all_ok()
        (self.state / "gamma.shared-client-id").touch()
        t = self.bar()["tooltip"]
        self.assertIn("gamma_remote", t)
        self.assertNotIn("alpha_remote", t)
        self.assertIn("drive-sync-oauth-client", t)

    def test_tooltip_has_failure_details_and_history_counts(self):
        self.all_ok()
        now = int(time.time())
        self.write_status("alpha", state="auth", message="Fix: rclone config reconnect alpha_remote:", streak=2,
                          first_fail_at=now - 60, last_ok=now - 600)
        (self.state / "history.jsonl").write_text(
            json.dumps({"name": "alpha", "result": "ok", "ended": now - 10}) + "\n"
            + json.dumps({"name": "alpha", "result": "auth", "ended": now - 9}) + "\n"
            + json.dumps({"name": "alpha", "result": "ok", "ended": now - 200000}) + "\n")
        t = self.bar()["tooltip"]
        self.assertIn("rclone config reconnect alpha_remote:", t)
        self.assertIn("2 failures", t)
        self.assertIn("24h: 1 ok, 1 failed", t)

    def test_tooltip_reports_inactive_timer(self):
        self.all_ok()
        p = self.stub / "systemctl.behave"
        p.write_text("#!/bin/bash\nexit 0\n")
        p.chmod(0o755)
        self.assertIn("Timer inactive", self.bar()["tooltip"])

    def test_output_is_one_json_line(self):
        self.all_ok()
        out = self.status_cmd("--json").stdout
        self.assertEqual(len(out.strip().splitlines()), 1)
        json.loads(out)

    def test_plain_text_mode_still_works(self):
        self.all_ok()
        out = self.status_cmd("--plain")
        self.assertEqual(out.returncode, 0)
        self.assertIn("synced", out.stdout)


class ResyncFlow(Sandbox):
    def flow(self, typed, mode="newer", env=None):
        return self.status_cmd("--resync-flow", "alpha", env=env, input=f"{mode}\n{typed}\n")

    def drive_sync_on_path(self):
        from tests.harness import script_path, write_exec
        write_exec(self.bin / "drive-sync", f'#!/bin/bash\nexec bash "{script_path("drive-sync")}" "$@"\n')
        return {"DRIVE_SYNC_BIN": str(self.bin / "drive-sync")}

    def test_wrong_typing_runs_only_preview_and_restores_timer(self):
        e = self.drive_sync_on_path()
        out = self.flow("yes", env=e)
        calls = self.calls()
        self.assertEqual(len(calls), 1, out.stdout + out.stderr)
        self.assertIn("--dry-run", calls[0])
        sc = self.calls("systemctl")
        self.assertTrue(any("stop drive-sync.timer" in c for c in sc))
        self.assertTrue(any("start drive-sync.timer" in c for c in sc))

    def test_exact_typing_runs_resync_with_chosen_mode_then_restores_timer(self):
        e = self.drive_sync_on_path()
        out = self.flow("RESYNC alpha", mode="path1", env=e)
        calls = self.calls()
        self.assertEqual(len(calls), 2, out.stdout + out.stderr)
        self.assertIn("--dry-run", calls[0])
        self.assertIn("--resync-mode path1", calls[1])
        self.assertNotIn("--dry-run", calls[1])
        self.assertIn("--backup-dir2", calls[1])
        sc = self.calls("systemctl")
        stop = next(i for i, c in enumerate(sc) if "stop drive-sync.timer" in c)
        start = next(i for i, c in enumerate(sc) if "start drive-sync.timer" in c)
        self.assertLess(stop, start)

    def test_preview_that_cannot_run_offline_stops_the_flow(self):
        from tests.harness import write_exec
        e = self.drive_sync_on_path()
        write_exec(self.stub / "curl.behave", "#!/bin/bash\nprintf 000\n")
        out = self.flow("RESYNC alpha", env=e)
        self.assertIn("Preview failed", out.stdout)
        self.assertEqual(self.calls(), [])
        self.assertTrue(any("start drive-sync.timer" in c for c in self.calls("systemctl")))

    def test_preview_that_loses_the_lock_stops_the_flow(self):
        import os
        from tests.harness import script_path, write_exec
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        # The lock is taken after the flow's own check, as a run starting at the wrong moment would.
        write_exec(self.bin / "drive-sync", f"""#!/bin/bash
flock "{lock}" sleep 2 >/dev/null 2>&1 &
sleep 0.3
DRIVE_SYNC_LOCK_WAIT=0 exec bash "{script_path('drive-sync')}" "$@"
""")
        out = self.flow("RESYNC alpha", env={"DRIVE_SYNC_BIN": str(self.bin / "drive-sync")})
        self.assertIn("Preview failed", out.stdout)
        self.assertEqual(self.calls(), [])

    def test_invalid_mode_refused(self):
        e = self.drive_sync_on_path()
        self.flow("RESYNC alpha", mode="older", env=e)
        self.assertEqual(self.calls(), [])

    def test_refused_while_a_sync_runs(self):
        import os, subprocess
        e = self.drive_sync_on_path()
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        holder = subprocess.Popen(["flock", str(lock), "sleep", "30"], env=self.env)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(0.3)
        self.flow("RESYNC alpha", env=e)
        self.assertEqual(self.calls(), [])


class Menu(Sandbox):
    def test_sync_now_marks_manual_and_starts_service(self):
        for r in self.REMOTES:
            self.old_status(r)
        out = self.status_cmd("--sync-now")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((self.tmp / "run/drive-sync/manual-request").exists())
        self.assertTrue(any("start --no-block drive-sync.service" in c for c in self.calls("systemctl")))

    def test_refresh_pattern_matches_new_and_old_tail_processes(self):
        from tests.harness import script_path
        src = script_path("drive-sync").read_text()
        pat = re.search(r"pkill -USR1 -f '([^']+)'", src).group(1)
        for cmd in ("/bin/bash /x/drive-sync-status --tail", "/bin/bash /x/drive-sync-status --waybar"):
            self.assertRegex(cmd, pat)


if __name__ == "__main__":
    unittest.main()
