"""Sandbox for drive-sync tests: temp HOME, stub tools, and no way to reach the real rclone."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
REAL_TOOLS = """bash sh awk gawk rg fd jq date sleep cut tail head sort comm tr stat mv rm cp mkdir gzip flock
dirname basename wc tee cat sed xargs mktemp id touch du env uniq cmp ln chmod tac""".split()
STUBS = ["curl", "nmcli", "notify-send", "pgrep", "pkill", "systemctl", "systemd-run", "rofi", "setsid", "thunar", "ghostty"]


def script_path(name):
    """Prefer the repo layout (dot_local/bin/executable_NAME), else the installed layout."""
    if os.environ.get("DRIVE_SYNC_BIN_DIR"):
        return Path(os.environ["DRIVE_SYNC_BIN_DIR"]) / name
    repo = HERE.parents[2] / "dot_local" / "bin" / f"executable_{name}"
    return repo if repo.exists() else Path.home() / ".local" / "bin" / name


def write_exec(path, text):
    path.unlink(missing_ok=True)  # never write through a symlink to a real tool
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class Sandbox(unittest.TestCase):
    REMOTES = ("alpha", "beta", "gamma")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drive-sync-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.stub = self.tmp / "stub"
        self.bin = self.tmp / "bin"
        for d in (self.home, self.stub, self.stub / "behave", self.bin, self.home / ".config/rclone",
                  self.home / ".config/drive-sync", self.tmp / "run", self.tmp / "power"):
            d.mkdir(parents=True)
        for tool in REAL_TOOLS:
            real = shutil.which(tool)
            self.assertIsNotNone(real, tool)
            (self.bin / tool).symlink_to(real)
        self._stubs()
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin), "STUB": str(self.stub),
            "XDG_RUNTIME_DIR": str(self.tmp / "run"), "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"), "XDG_CONFIG_HOME": str(self.home / ".config"),
            "DRIVE_SYNC_POWER_DIR": str(self.tmp / "power"), "TERMINAL": "ghostty",
        }
        found = shutil.which("rclone", path=self.env["PATH"])
        if found != str(self.bin / "rclone"):
            self.fail(f"refusing to run: rclone resolves to {found}")
        (self.home / ".config/rclone/bisync-filters.txt").write_text("- *.tmp\n")
        self.state = self.home / ".local/state/drive-sync"
        self.state.mkdir(parents=True)
        self.cache = self.home / ".cache/rclone/bisync"
        self.cache.mkdir(parents=True)
        conf = "# comment\n"
        for r in self.REMOTES:
            (self.home / "drive" / r).mkdir(parents=True)
            conf += f"{r}|{r}_remote:|~/drive/{r}|Label\n"
        (self.home / ".config/drive-sync/remotes.conf").write_text(conf)

    def _stubs(self):
        write_exec(self.bin / "rclone", """#!/bin/bash
printf '%s\\n' "$*" >>"$STUB/rclone.calls"
[ "$1" = bisync ] || exit 0
r="${2%:}"
if [ -x "$STUB/behave/$r" ]; then exec "$STUB/behave/$r" "$@"; fi
echo "2026/01/01 00:00:00 INFO  : No changes found"
echo "2026/01/01 00:00:00 INFO  : Bisync successful"
""")
        for name in STUBS:
            write_exec(self.bin / name, f'#!/bin/bash\nprintf \'%s\\n\' "$*" >>"$STUB/{name}.calls"\n'
                       f'[ -x "$STUB/{name}.behave" ] && exec "$STUB/{name}.behave" "$@"\nexit 0\n')
        write_exec(self.stub / "curl.behave", "#!/bin/bash\nprintf 401\n")
        write_exec(self.stub / "nmcli.behave", "#!/bin/bash\necho full\n")

    # --- running -----------------------------------------------------------------
    def cmd(self, name):
        """Run through bash: chezmoi source files are not executable."""
        return [str(self.bin / "bash"), str(script_path(name))]

    def sync(self, *args, timer=True, env=None, timeout=60):
        e = dict(self.env)
        if timer:
            e["DRIVE_SYNC_TIMER"] = "1"
        e.update(env or {})
        return subprocess.run([*self.cmd("drive-sync"), *args], env=e, text=True,
                              capture_output=True, timeout=timeout)

    def status_cmd(self, *args, env=None, timeout=30, input=None):
        e = dict(self.env)
        e.update(env or {})
        return subprocess.run([*self.cmd("drive-sync-status"), *args], env=e, text=True,
                              capture_output=True, timeout=timeout, input=input)

    def bar(self, env=None):
        out = self.status_cmd("--json", env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout.strip().splitlines()[-1])

    # --- behaviours and state ------------------------------------------------------
    def behave(self, remote, script):
        write_exec(self.stub / "behave" / f"{remote}_remote", "#!/bin/bash\n" + script + "\n")

    def behave_fixture(self, remote, fixture, rc):
        self.behave(remote, f'cat "{FIXTURES / fixture}"; exit {rc}')

    def calls(self, tool="rclone"):
        p = self.stub / f"{tool}.calls"
        return p.read_text().splitlines() if p.exists() else []

    def status(self, name):
        p = self.state / f"{name}.status"
        if not p.exists():
            return {}
        return dict(l.split("=", 1) for l in p.read_text().splitlines() if "=" in l)

    def write_status(self, name, **kv):
        (self.state / f"{name}.status").write_text("".join(f"{k}={v}\n" for k, v in kv.items()))

    def old_status(self, name, state="ok", last_ok=None):
        """Status file exactly as the previous version wrote it."""
        now = int(time.time())
        last_ok = now if last_ok is None else last_ok
        self.write_status(name, state=state, message="Synced", last_run=now, last_ok=last_ok,
                          notified_state="", notified_at=0)

    def listing(self, remote, files, side=2):
        """Write bisync's saved listing and create the matching local files."""
        key = str(self.home / "drive" / remote).lstrip("/").replace("/", "_")
        lst = self.cache / f"{remote}_remote_..{key}.path{side}.lst"
        lines = ["# bisync listing v1 from test"]
        for f in files:
            lines.append(f'- 5 - - 2026-02-26T15:31:31.000000000+0000 "{f}"')
            p = self.home / "drive" / remote / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("hello")
        lst.write_text("\n".join(lines) + "\n")

    def remove_local(self, remote, files):
        for f in files:
            (self.home / "drive" / remote / f).unlink()

    def history(self):
        p = self.state / "history.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def battery(self, status, capacity):
        b = self.tmp / "power" / "BAT0"
        b.mkdir(exist_ok=True)
        (b / "status").write_text(status + "\n")
        (b / "capacity").write_text(f"{capacity}\n")
