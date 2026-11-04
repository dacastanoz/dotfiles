import os
import signal
import subprocess
import time
import unittest

from tests.harness import FIXTURES, Sandbox, script_path, write_exec


class Compatibility(Sandbox):
    def test_old_status_files_are_read_and_upgraded(self):
        for r in self.REMOTES:
            self.old_status(r)
        out = self.sync()
        self.assertEqual(out.returncode, 0, out.stderr)
        for r in self.REMOTES:
            self.assertEqual(self.status(r)["state"], "ok")
            self.assertEqual(self.status(r)["streak"], "0")
        self.assertFalse([c for c in self.calls() if "--resync" in c or "--force" in c])

    def test_required_flags_stay(self):
        self.sync()
        c = self.calls()[0]
        for flag in ("--check-access", "--resilient", "--recover", "--max-delete 30", "--conflict-resolve newer",
                     "--conflict-loser num", "--backup-dir2", "--filters-file"):
            self.assertIn(flag, c)
        self.assertNotIn("--drive-skip-gdocs", c)


class NoAutoResync(Sandbox):
    def test_timer_never_passes_resync(self):
        self.behave_fixture("alpha", "needs_resync.log", 7)
        for _ in range(3):
            self.sync()
        self.assertFalse([c for c in self.calls() if "--resync" in c])

    def test_resync_refused_without_confirmation(self):
        out = self.sync("--resync", "alpha", timer=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_resync_refused_under_timer_even_when_confirmed(self):
        out = self.sync("--resync", "--confirmed", "alpha", timer=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_confirmed_resync_has_backup_dir_and_chosen_mode(self):
        out = self.sync("--resync", "--resync-mode", "path1", "--confirmed", "alpha", timer=False)
        self.assertEqual(out.returncode, 0, out.stderr)
        c = self.calls()[0]
        self.assertIn("--resync", c)
        self.assertIn("--resync-mode path1", c)
        self.assertIn("--backup-dir2", c)

    def test_preview_is_dry_run_and_leaves_state(self):
        self.old_status("alpha", state="needs-resync")
        out = self.sync("--resync-preview", "--resync-mode", "newer", "alpha", timer=False)
        self.assertEqual(out.returncode, 0, out.stderr)
        c = self.calls()[0]
        self.assertIn("--dry-run", c)
        self.assertIn("--resync", c)
        self.assertEqual(self.status("alpha")["state"], "needs-resync")
        self.assertFalse((self.state / "alpha.verify").exists())

    def test_filters_file_unchanged(self):
        before = (self.home / ".config/rclone/bisync-filters.txt").read_bytes()
        self.sync()
        self.assertEqual((self.home / ".config/rclone/bisync-filters.txt").read_bytes(), before)


class StateMachine(Sandbox):
    def test_quota_backoff_ladder(self):
        self.behave_fixture("alpha", "quota_403.log", 7)
        expected = [10, 20, 40, 60, 60]
        for minutes in expected:
            st = self.status("alpha")
            if st:
                self.write_status("alpha", **{**st, "next_attempt": "0"})
            t0 = int(time.time())
            self.sync("alpha")
            st = self.status("alpha")
            self.assertEqual(st["state"], "rate-limited")
            self.assertAlmostEqual(int(st["next_attempt"]) - t0, minutes * 60, delta=15)

    def test_backoff_skips_timer_only_that_remote(self):
        self.write_status("alpha", state="rate-limited", message="x", last_ok=int(time.time()),
                          next_attempt=int(time.time()) + 600, fail_class="rate-limited", streak=1, first_fail_at=1)
        self.sync()
        calls = [c.split()[1] for c in self.calls()]
        self.assertNotIn("alpha_remote:", calls)
        self.assertIn("beta_remote:", calls)
        self.assertEqual(self.status("alpha")["state"], "rate-limited")

    def test_manual_run_ignores_backoff(self):
        self.write_status("alpha", state="rate-limited", message="x", next_attempt=int(time.time()) + 600,
                          fail_class="rate-limited", streak=1)
        self.sync("alpha", timer=False)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.status("alpha")["state"], "ok")
        self.assertEqual(self.status("alpha")["next_attempt"], "0")

    def test_menu_request_counts_as_manual_once(self):
        self.write_status("alpha", state="rate-limited", message="x", next_attempt=int(time.time()) + 600,
                          fail_class="rate-limited", streak=1)
        d = self.tmp / "run" / "drive-sync"
        d.mkdir(parents=True, exist_ok=True)
        (d / "manual-request").touch()
        self.sync()
        self.assertIn("alpha_remote:", [c.split()[1] for c in self.calls()])
        self.assertFalse((d / "manual-request").exists())

    def test_rotation_changes_first_remote(self):
        firsts = []
        for _ in range(3):
            (self.stub / "rclone.calls").unlink(missing_ok=True)
            self.sync()
            firsts.append(self.calls()[0].split()[1])
        self.assertEqual(len(set(firsts)), 3)

    def test_needs_resync_blocks_timer_but_not_manual(self):
        self.behave_fixture("alpha", "needs_resync.log", 7)
        self.sync("alpha")
        self.assertEqual(self.status("alpha")["state"], "needs-resync")
        n = len(self.calls())
        self.sync("alpha")
        self.assertEqual(len(self.calls()), n)
        self.sync("alpha", timer=False)
        self.assertEqual(len(self.calls()), n + 1)
        self.assertFalse([c for c in self.calls() if "--resync" in c])

    def test_gdoc_edit_stops_remote_and_keeps_name_local(self):
        self.behave_fixture("alpha", "gdoc_edit.log", 7)
        self.sync("alpha")
        st = self.status("alpha")
        self.assertEqual(st["state"], "gdoc-edit")
        self.assertIn("browser", st["message"].lower())
        self.assertIn("document-a.docx", st["detail"])
        notes = "\n".join(self.calls("notify-send"))
        self.assertIn("critical", notes)
        self.assertNotIn("document-a", notes)
        n = len(self.calls())
        self.sync("alpha")
        self.assertEqual(len(self.calls()), n)
        self.assertFalse([c for c in self.calls() if "--resync" in c])

    def test_real_error_line_is_stored_even_with_noise_after(self):
        noise = "".join(f'2026/01/01 00:00:00 INFO  : line {i}\\n' for i in range(50))
        self.behave("alpha", f'cat "{FIXTURES / "unknown.log"}"; printf "{noise}"; exit 1')
        self.sync("alpha")
        self.assertIn("unexpected internal failure", self.status("alpha")["detail"])

    def test_auth_uses_real_rclone_remote_in_command(self):
        self.behave_fixture("alpha", "auth_invalid_client.log", 7)
        self.sync("alpha")
        self.assertEqual(self.status("alpha")["state"], "auth")
        self.assertIn("rclone config reconnect alpha_remote:", self.status("alpha")["message"])

    def test_repeated_auth_stops_with_hourly_probe_and_critical(self):
        self.behave_fixture("alpha", "auth_401.log", 7)
        self.sync("alpha")
        self.assertEqual(self.calls("notify-send"), [])
        self.assertEqual(self.status("alpha")["next_attempt"], "0")
        self.sync("alpha")
        st = self.status("alpha")
        self.assertGreater(int(st["next_attempt"]), time.time() + 3000)
        notes = "\n".join(self.calls("notify-send"))
        self.assertIn("critical", notes)
        self.assertIn("rclone config reconnect alpha_remote:", notes)

    def test_success_clears_failure_counters(self):
        self.behave_fixture("alpha", "auth_401.log", 7)
        self.sync("alpha")
        (self.stub / "behave" / "alpha_remote").unlink()
        self.sync("alpha")
        st = self.status("alpha")
        self.assertEqual((st["state"], st["streak"], st["fail_class"], st["next_attempt"]), ("ok", "0", "", "0"))


class Notifications(Sandbox):
    def notes(self):
        return self.calls("notify-send")

    def test_single_quota_is_silent_then_notifies_after_two_hours(self):
        self.behave_fixture("alpha", "quota_403.log", 7)
        self.sync("alpha")
        quota = lambda: [n for n in self.notes() if "shared client" not in n]
        self.assertEqual(quota(), [])
        st = self.status("alpha")
        self.write_status("alpha", **{**st, "first_fail_at": int(time.time()) - 7300, "next_attempt": 0})
        self.sync("alpha")
        self.assertEqual(len(quota()), 1)

    def test_offline_never_notifies(self):
        self.behave_fixture("alpha", "dns.log", 7)
        for _ in range(3):
            self.sync("alpha")
        self.assertEqual(self.notes(), [])
        self.assertEqual(self.status("alpha")["state"], "offline")

    def test_interrupted_only_when_repeated(self):
        self.behave_fixture("alpha", "graceful.log", 143)
        self.sync("alpha")
        self.sync("alpha")
        self.assertEqual(self.notes(), [])
        self.sync("alpha")
        self.assertEqual(len(self.notes()), 1)

    def test_error_after_two_consecutive(self):
        self.behave_fixture("alpha", "unknown.log", 1)
        self.sync("alpha")
        self.assertEqual(self.notes(), [])
        self.sync("alpha")
        self.assertEqual(len(self.notes()), 1)

    def test_shared_client_warning_once_a_day_naming_only_affected(self):
        self.behave("alpha", f'cat "{FIXTURES / "quota_403.log"}" | head -1; echo ok; exit 0')
        self.sync()
        self.sync()
        notes = [n for n in self.notes() if "client" in n.lower()]
        self.assertEqual(len(notes), 1)
        self.assertIn("alpha_remote", notes[0])
        self.assertNotIn("beta_remote", notes[0])
        self.assertIn("drive-sync-oauth-client", notes[0])

    def test_shared_client_marker_clears_after_switch(self):
        self.behave("alpha", f'cat "{FIXTURES / "quota_403.log"}" | head -1; exit 0')
        self.sync("alpha")
        self.assertTrue((self.state / "alpha.shared-client-id").exists())
        (self.stub / "behave" / "alpha_remote").unlink()
        self.sync("alpha")
        self.assertFalse((self.state / "alpha.shared-client-id").exists())

    def test_shared_client_marker_kept_when_run_fails_without_notice(self):
        (self.state / "alpha.shared-client-id").touch()
        self.behave_fixture("alpha", "dns.log", 7)
        self.sync("alpha")
        self.assertTrue((self.state / "alpha.shared-client-id").exists())

    def test_stale_failing_remote_warns(self):
        self.behave_fixture("alpha", "prior_lock.log", 1)
        self.old_status("alpha", last_ok=int(time.time()) - 8 * 3600)
        self.sync("alpha")
        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertIn("alpha", notes[0])


class NetworkErrorsWhileOnline(Sandbox):
    def attempt(self):
        st = self.status("alpha")
        if st:
            self.write_status("alpha", **{**st, "next_attempt": "0"})
        self.sync("alpha")

    def test_persistent_timeout_backs_off_and_reaches_a_notification(self):
        self.behave_fixture("alpha", "timeout_deadline.log", 7)
        now = int(time.time())
        self.old_status("alpha", last_ok=now - 600)
        t0 = int(time.time())
        self.attempt()
        st = self.status("alpha")
        self.assertEqual((st["state"], st["streak"], st["fail_class"]), ("network", "1", "network"))
        self.assertAlmostEqual(int(st["next_attempt"]) - t0, 600, delta=15)
        self.assertEqual(self.calls("notify-send"), [])
        self.attempt()
        self.assertEqual(self.calls("notify-send"), [])
        self.attempt()
        self.assertEqual(self.status("alpha")["streak"], "3")
        self.assertEqual(len(self.calls("notify-send")), 1)

    def test_timer_respects_the_backoff(self):
        self.behave_fixture("alpha", "timeout_io.log", 7)
        self.sync("alpha")
        n = len(self.calls())
        self.sync("alpha")
        self.assertEqual(len(self.calls()), n)

    def test_stale_notification_covers_network(self):
        self.behave_fixture("alpha", "connection_reset.log", 7)
        self.old_status("alpha", last_ok=int(time.time()) - 8 * 3600)
        self.sync("alpha")
        self.assertTrue([n for n in self.calls("notify-send") if "out of date" in n])

    def test_success_clears_it(self):
        self.behave_fixture("alpha", "timeout_io.log", 7)
        self.sync("alpha")
        (self.stub / "behave" / "alpha_remote").unlink()
        self.sync("alpha", timer=False)
        st = self.status("alpha")
        self.assertEqual((st["state"], st["streak"], st["next_attempt"]), ("ok", "0", "0"))

    def test_connection_really_lost_during_the_run_stays_offline(self):
        self.behave_fixture("alpha", "timeout_io.log", 7)
        write_exec(self.stub / "curl.behave", """#!/bin/bash
if [ -e "$STUB/probed" ]; then printf 000; else : >"$STUB/probed"; printf 401; fi
""")
        self.sync("alpha")
        st = self.status("alpha")
        self.assertEqual(st["state"], "offline")
        self.assertEqual(st.get("next_attempt", "0"), "0")
        self.assertEqual(self.calls("notify-send"), [])


class ResyncPreviewMustRun(Sandbox):
    def test_preview_offline_fails_visibly(self):
        write_exec(self.stub / "curl.behave", "#!/bin/bash\nprintf 000\n")
        self.old_status("alpha")
        out = self.sync("--resync-preview", "alpha", timer=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("offline", (out.stdout + out.stderr).lower())
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.status("alpha")["state"], "ok")

    def test_preview_lock_busy_fails_visibly(self):
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        holder = subprocess.Popen(["flock", str(lock), "sleep", "30"], env=self.env)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(0.3)
        out = self.sync("--resync-preview", "alpha", timer=False, env={"DRIVE_SYNC_LOCK_WAIT": "0"})
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("running", (out.stdout + out.stderr).lower())
        self.assertEqual(self.calls(), [])

    def test_confirmed_resync_offline_is_not_reported_as_success(self):
        write_exec(self.stub / "curl.behave", "#!/bin/bash\nprintf 000\n")
        out = self.sync("--resync", "--confirmed", "alpha", timer=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.calls(), [])


class ListingNames(Sandbox):
    REMOTES = ("my drive", "beta")

    def key_listing(self, remote, files, rclone_key):
        self.listing(remote, files)
        made = next(self.cache.glob(f"{remote}_remote_*.path2.lst"))
        made.rename(self.cache / f"{remote.replace(' ', '_')}_remote_..{rclone_key}.path2.lst")

    def setup_spaced(self):
        files = [f"f{i}.txt" for i in range(50)]
        key = str(self.home / "drive" / "my drive").lstrip("/").replace("/", "_").replace(" ", "_")
        self.key_listing("my drive", files, key)
        self.remove_local("my drive", files)

    def test_delete_cap_finds_the_listing_of_a_path_with_a_space(self):
        self.setup_spaced()
        self.sync("my drive")
        self.assertEqual(self.status("my drive")["state"], "delete-cap")
        self.assertEqual(self.status("my drive")["delete_count"], "50")

    def test_status_finds_the_same_listing(self):
        self.setup_spaced()
        out = self.status_cmd("--pending", "my drive")
        self.assertEqual(out.stdout.split()[2], "50", out.stdout + out.stderr)


class Battery(Sandbox):
    def test_timer_below_floor_skips_and_writes_state(self):
        self.battery("Discharging", 19)
        for r in self.REMOTES:
            self.old_status(r)
        self.sync()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.status("alpha")["state"], "battery-skip")
        self.assertEqual(self.calls("curl"), [])

    def test_timer_at_floor_runs(self):
        self.battery("Discharging", 20)
        self.sync()
        self.assertEqual(len(self.calls()), 3)

    def test_charging_runs(self):
        self.battery("Charging", 5)
        self.sync()
        self.assertEqual(len(self.calls()), 3)

    def test_manual_allowed(self):
        self.battery("Discharging", 5)
        self.sync(timer=False)
        self.assertEqual(len(self.calls()), 3)

    def test_skip_does_not_hide_blocking_state(self):
        self.battery("Discharging", 5)
        self.old_status("alpha", state="needs-resync")
        self.sync()
        self.assertEqual(self.status("alpha")["state"], "needs-resync")

    def test_offline_does_not_hide_blocking_state(self):
        (self.stub / "curl.behave").write_text("#!/bin/bash\nprintf 000\n")
        self.old_status("alpha", state="auth")
        self.old_status("beta", state="ok")
        self.sync()
        self.assertEqual(self.status("alpha")["state"], "auth")
        self.assertEqual(self.status("beta")["state"], "offline")


class DeleteCap(Sandbox):
    def files(self, n):
        return [f"dir/f{i}.txt" for i in range(n)]

    def test_small_tree_floor_20(self):
        self.listing("alpha", self.files(100))
        self.remove_local("alpha", self.files(100)[:20])
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1, "20 deletions is at the floor and allowed")
        self.listing("beta", self.files(100))
        self.remove_local("beta", self.files(100)[:21])
        self.sync("beta")
        self.assertEqual(self.status("beta")["state"], "delete-cap")
        self.assertFalse([c for c in self.calls() if "beta_remote" in c])

    def test_ten_percent_over_floor(self):
        self.listing("alpha", self.files(400))
        self.remove_local("alpha", self.files(400)[:41])
        self.sync("alpha")
        self.assertEqual(self.status("alpha")["state"], "delete-cap")
        self.assertEqual(self.status("alpha")["delete_count"], "41")

    def test_absolute_100_on_large_tree(self):
        self.listing("alpha", self.files(3000))
        self.remove_local("alpha", self.files(3000)[:100])
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1)
        self.listing("beta", self.files(3000))
        self.remove_local("beta", self.files(3000)[:101])
        self.sync("beta")
        self.assertEqual(self.status("beta")["state"], "delete-cap")

    def test_blocked_remote_does_not_stop_others(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync()
        remotes = [c.split()[1] for c in self.calls()]
        self.assertEqual(sorted(remotes), ["beta_remote:", "gamma_remote:"])

    def test_notification_has_count_but_no_names_and_sample_is_private(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("alpha")
        notes = "\n".join(self.calls("notify-send"))
        self.assertIn("critical", notes)
        self.assertIn("50", notes)
        self.assertNotIn("f1.txt", notes)
        log = (self.home / ".local/share/rclone/bisync.log").read_text()
        self.assertNotIn("f1.txt", log)
        sample = self.state / "alpha.delete-sample"
        self.assertIn("dir/f", sample.read_text())
        self.assertEqual(sample.stat().st_mode & 0o077, 0)

    def test_restoring_files_unblocks_automatically(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("alpha")
        self.listing("alpha", self.files(50))
        self.sync("alpha")
        self.assertEqual(self.status("alpha")["state"], "ok")

    def test_manual_run_is_still_capped(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("alpha", timer=False)
        self.assertEqual(self.calls(), [])

    def test_force_bypasses_cap(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("--force", "alpha", timer=False)
        self.assertIn("--force", self.calls()[0])

    def test_present_files_with_quotes_and_accents_are_not_counted(self):
        self.listing("alpha", ["ñandú/canción á.txt"] + self.files(10))
        path = self.home / "drive/alpha" / 'say "hi".txt'
        path.write_text("x")
        lst = next(self.cache.glob("alpha_remote_*.path2.lst"))
        lst.write_text(lst.read_text() + '- 1 - - 2026-02-26T15:31:31.000000000+0000 "say \\"hi\\".txt"\n')
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1)
        self.remove_local("alpha", ["ñandú/canción á.txt"])
        path.unlink()
        self.assertEqual(self.status("alpha")["state"], "ok")

    def test_no_listing_means_no_cap(self):
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1)

    def approve(self, remote, typed):
        return self.status_cmd("--allow-deletes", remote, "--typed", typed)

    def test_override_requires_exact_typing_and_is_one_time(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("alpha")
        bad = self.approve("alpha", "yes")
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse((self.state / "alpha.delete-override").exists())
        good = self.approve("alpha", "DELETE 50")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn("--force", self.calls()[0])
        self.assertFalse((self.state / "alpha.delete-override").exists())
        # Stub did not update the listing, so the same deletions block the next run again.
        self.sync("alpha")
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.status("alpha")["state"], "delete-cap")

    def test_override_applies_to_that_remote_only(self):
        for r in ("alpha", "beta"):
            self.listing(r, self.files(50))
            self.remove_local(r, self.files(50))
        self.sync()
        self.assertEqual(self.approve("alpha", "DELETE 50").returncode, 0)
        self.sync()
        remotes = [c.split()[1] for c in self.calls()]
        self.assertIn("alpha_remote:", remotes)
        self.assertNotIn("beta_remote:", remotes)

    def test_override_does_not_cover_more_deletions_than_approved(self):
        self.listing("alpha", self.files(60))
        self.remove_local("alpha", self.files(60)[:30])
        self.sync("alpha")
        self.assertEqual(self.approve("alpha", "DELETE 30").returncode, 0)
        self.remove_local("alpha", self.files(60)[30:50])
        self.sync("alpha")
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.state / "alpha.delete-override").exists())

    def test_expired_override_is_ignored(self):
        self.listing("alpha", self.files(50))
        self.remove_local("alpha", self.files(50))
        self.sync("alpha")
        self.assertEqual(self.approve("alpha", "DELETE 50").returncode, 0)
        (self.state / "alpha.delete-override").write_text(f"approved_count=50\ncreated_at={int(time.time()) - 90000}\n")
        self.sync("alpha")
        self.assertEqual(self.calls(), [])


class Watchdog(Sandbox):
    env_fast = {"DRIVE_SYNC_WATCHDOG_SECONDS": "3", "DRIVE_SYNC_KILL_GRACE": "1"}

    def test_silent_run_is_killed_and_others_continue(self):
        self.behave("alpha", 'echo "2026/01/01 00:00:00 INFO  : Building Path1 and Path2 listings"; exec sleep 300')
        out = self.sync(env=self.env_fast)
        self.assertEqual(self.status("alpha")["state"], "hung")
        self.assertEqual(self.status("beta")["state"], "ok")
        self.assertFalse((self.state / "alpha.running").exists())
        self.assertEqual(self.calls("notify-send"), [])

    def test_lock_renewal_and_zero_stats_are_not_progress(self):
        self.behave("alpha", """while :; do
echo "2026/01/01 00:00:00 NOTICE:           0 B / 0 B, -, 0 B/s, ETA -"
echo "2026/01/01 00:00:00 INFO  : lock file renewed for 2m0s."
sleep 0.5; done""")
        self.sync("alpha", env=self.env_fast)
        self.assertEqual(self.status("alpha")["state"], "hung")

    def test_progressing_upload_is_never_killed(self):
        self.behave("alpha", """for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
echo "2026/01/01 00:00:00 NOTICE:   $i.000 MiB / 100.000 MiB, $i%, 1 MiB/s, ETA 1m"
sleep 0.5; done""")
        self.sync("alpha", env=self.env_fast)
        self.assertEqual(self.status("alpha")["state"], "ok")

    def test_second_hang_notifies(self):
        self.behave("alpha", "exec sleep 300")
        self.sync("alpha", env=self.env_fast)
        self.assertEqual(self.calls("notify-send"), [])
        self.sync("alpha", env=self.env_fast)
        self.assertEqual(len(self.calls("notify-send")), 1)


class DeadRuns(Sandbox):
    def running_file(self, name, boot="other-boot"):
        (self.state / f"{name}.running").write_text(
            f"started={int(time.time()) - 100}\npid=999999\nboot_id={boot}\nmode=normal\ntrigger=timer\n")

    def test_next_run_records_dead_run_from_other_boot_and_retries(self):
        self.old_status("alpha")
        self.running_file("alpha")
        self.sync()
        hist = [h for h in self.history() if h["name"] == "alpha"]
        self.assertEqual(hist[0]["result"], "interrupted")
        self.assertIn("restart", hist[0]["reason"])
        self.assertEqual(self.status("alpha")["state"], "ok")
        self.assertFalse((self.state / "alpha.running").exists())

    def test_post_stop_records_oom(self):
        self.old_status("alpha")
        self.running_file("alpha", boot="same")
        out = self.sync("--post-stop", env={"SERVICE_RESULT": "oom-kill", "EXIT_CODE": "killed", "EXIT_STATUS": "9"})
        self.assertEqual(out.returncode, 0, out.stderr)
        st = self.status("alpha")
        self.assertEqual(st["state"], "interrupted")
        self.assertIn("memory", st["message"].lower())
        self.assertEqual(st["streak"], "1")
        self.assertFalse((self.state / "alpha.running").exists())
        self.assertEqual(self.calls(), [])

    def test_post_stop_after_success_is_a_noop(self):
        self.old_status("alpha")
        out = self.sync("--post-stop", env={"SERVICE_RESULT": "success"})
        self.assertEqual(out.returncode, 0)
        self.assertEqual(self.status("alpha")["state"], "ok")
        self.assertEqual(self.history(), [])

    def test_post_stop_leaves_a_live_run_alone(self):
        self.running_file("alpha")
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        holder = subprocess.Popen(["flock", str(lock), "sleep", "30"], env=self.env)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(0.3)
        self.sync("--post-stop", env={"SERVICE_RESULT": "exit-code"})
        self.assertTrue((self.state / "alpha.running").exists())

    def test_sigterm_records_interrupted_and_stops_rclone(self):
        self.behave("alpha", "exec sleep 300")
        self.old_status("alpha")
        e = dict(self.env, DRIVE_SYNC_TIMER="1")
        p = subprocess.Popen([*self.cmd("drive-sync"), "alpha"], env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if (self.state / "alpha.running").exists() and self.calls():
                break
            time.sleep(0.1)
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=15)
        st = self.status("alpha")
        self.assertEqual(st["state"], "interrupted")
        self.assertFalse((self.state / "alpha.running").exists())
        self.assertFalse((self.tmp / "run/drive-sync/progress").exists())
        self.assertEqual([h["result"] for h in self.history()], ["interrupted"])

    def test_timer_skip_when_locked(self):
        lock = self.tmp / "run" / f"drive-sync-{os.getuid()}.lock"
        holder = subprocess.Popen(["flock", str(lock), "sleep", "30"], env=self.env)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(0.3)
        out = self.sync(env={"DRIVE_SYNC_LOCK_WAIT": "0"})
        self.assertEqual(out.returncode, 0)
        self.assertEqual(self.calls(), [])


class History(Sandbox):
    def test_one_line_per_run_per_remote_without_file_names(self):
        self.behave("alpha", 'echo "2026/01/01 00:00:00 INFO  : - Path1    Queue copy to Path2    - secret/name.txt"; echo ok')
        self.sync()
        hist = self.history()
        self.assertEqual(sorted(h["name"] for h in hist), list(self.REMOTES))
        self.assertEqual({h["result"] for h in hist}, {"ok"})
        self.assertEqual({h["trigger"] for h in hist}, {"timer"})
        self.assertNotIn("secret", (self.state / "history.jsonl").read_text())
        self.assertEqual([h for h in hist if h["name"] == "alpha"][0]["counts"]["down"], 1)

    def test_bounded(self):
        self.state.joinpath("history.jsonl").write_text('{"name":"x","result":"ok"}\n' * 60000)
        self.sync(env={"DRIVE_SYNC_HISTORY_MAX_BYTES": "100000"})
        self.assertLess(self.state.joinpath("history.jsonl").stat().st_size, 100000)
        self.assertEqual(self.history()[-1]["result"], "ok")

    def test_failed_log_kept_without_stats_after_later_success(self):
        self.behave("alpha", f'echo "2026/01/01 00:00:00 NOTICE:   0 B / 0 B, -, 0 B/s, ETA -"; cat "{FIXTURES / "unknown.log"}"; exit 1')
        self.sync("alpha")
        (self.stub / "behave" / "alpha_remote").unlink()
        self.sync("alpha")
        kept = (self.state / "alpha.last-failed.log").read_text()
        self.assertIn("unexpected internal failure", kept)
        self.assertNotIn("0 B / 0 B", kept)

    def test_duplicates_collapse_to_a_count(self):
        dup = 'echo "2026/01/01 00:00:00 NOTICE: a/b.txt: Duplicate object found in source - ignoring"'
        self.behave("alpha", f"{dup}; {dup}; {dup}; exit 0")
        self.sync("alpha")
        log = (self.home / ".local/share/rclone/bisync.log").read_text()
        self.assertNotIn("Duplicate object", log)
        self.assertEqual(self.status("alpha")["duplicates"], "3")


class Safety(unittest.TestCase):
    def test_scripts_only_call_rclone_by_name(self):
        for name in ("drive-sync", "drive-sync-status"):
            self.assertNotIn("/usr/bin/rclone", script_path(name).read_text())


if __name__ == "__main__":
    unittest.main()
