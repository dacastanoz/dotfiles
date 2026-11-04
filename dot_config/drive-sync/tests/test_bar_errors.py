import subprocess
import unittest

from tests.harness import Sandbox, script_path, write_exec


class BarErrorsTail(Sandbox):
    def run_tail(self, rc):
        write_exec(self.bin / "module", f"#!/bin/bash\necho line\nexit {rc}\n")
        return subprocess.run([*self.cmd("bar-errors"), "tail", "drive-sync", str(self.bin / "module")], env=self.env,
                              text=True, capture_output=True, timeout=5)

    def log(self):
        p = self.home / ".cache/bar-errors.log"
        return p.read_text() if p.exists() else ""

    def test_closed_bar_pipe_is_not_an_error(self):
        out = self.run_tail(141)
        self.assertEqual(self.log(), "")
        self.assertEqual(out.stdout.strip(), "line")

    def test_termination_is_not_an_error(self):
        self.run_tail(143)
        self.assertEqual(self.log(), "")

    def test_real_failure_is_logged(self):
        write_exec(self.bin / "sleep", "#!/bin/bash\nexit 0\n")
        self.run_tail(3)
        self.assertIn("exited with code 3", self.log())


if __name__ == "__main__":
    unittest.main()
