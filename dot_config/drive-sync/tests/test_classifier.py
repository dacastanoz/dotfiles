import subprocess
import unittest

from tests.harness import FIXTURES, Sandbox


class Classifier(Sandbox):
    def classify(self, fixture, rc):
        out = subprocess.run([*self.cmd("drive-sync"), "--classify-log", str(FIXTURES / fixture), str(rc)],
                             env=self.env, text=True, capture_output=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_real_patterns(self):
        cases = [
            ("quota_403.log", 7, "rate-limited"),
            ("march_quota.log", 7, "rate-limited"),
            ("auth_401.log", 7, "auth"),
            ("auth_invalid_client.log", 7, "auth"),
            ("dns.log", 7, "offline"),
            ("oauth_network.log", 7, "offline"),
            ("timeout_deadline.log", 7, "network"),
            ("timeout_io.log", 7, "network"),
            ("connection_reset.log", 7, "network"),
            ("prior_lock.log", 1, "locked"),
            ("graceful.log", 143, "interrupted"),
            ("needs_resync.log", 7, "needs-resync"),
            ("too_many_deletes.log", 7, "too-many-deletes"),
            ("gdoc_edit.log", 7, "gdoc-edit"),
            ("access_check.log", 7, "access-check"),
            ("unknown.log", 1, "error"),
        ]
        for fixture, rc, want in cases:
            with self.subTest(fixture):
                self.assertEqual(self.classify(fixture, rc), want)

    def test_low_level_retry_noise_does_not_win(self):
        self.assertEqual(self.classify("retried_ratelimit_then_other.log", 1), "error")

    def test_kill_signal_exit_is_interrupted_whatever_the_log(self):
        self.assertEqual(self.classify("unknown.log", 137), "interrupted")

    def test_fixtures_hold_no_private_paths(self):
        for f in FIXTURES.iterdir():
            self.assertNotIn("/home/", f.read_text(), f.name)


if __name__ == "__main__":
    unittest.main()
