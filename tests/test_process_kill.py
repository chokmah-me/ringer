#!/usr/bin/env python3
"""Windows-safe process tree kill helpers used by worker timeouts and Ctrl+C."""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402


class ProcessKillHelperTests(unittest.TestCase):
    def test_windows_taskkill_tree_builds_force_and_soft_commands(self) -> None:
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
            calls.append(list(args))
            return SimpleNamespace(returncode=0)

        with mock.patch.object(ringer.subprocess, "run", side_effect=fake_run):
            ringer._windows_taskkill_tree(4242, force=False)
            ringer._windows_taskkill_tree(4242, force=True)

        self.assertEqual(
            calls,
            [
                ["taskkill", "/PID", "4242", "/T"],
                ["taskkill", "/PID", "4242", "/T", "/F"],
            ],
        )

    def test_terminate_and_kill_use_taskkill_on_windows(self) -> None:
        terminate_calls: list[bool] = []
        kill_calls: list[bool] = []
        tree_calls: list[bool] = []
        proc = SimpleNamespace(
            pid=7777,
            terminate=lambda: terminate_calls.append(True),
            kill=lambda: kill_calls.append(True),
        )

        def fake_tree(pid: int, *, force: bool) -> None:
            self.assertEqual(pid, 7777)
            tree_calls.append(force)

        with (
            mock.patch.object(ringer.os, "name", "nt"),
            mock.patch.object(ringer, "_windows_taskkill_tree", side_effect=fake_tree),
        ):
            ringer.terminate_process_group(proc)  # type: ignore[arg-type]
            ringer.kill_process_group(proc)  # type: ignore[arg-type]

        self.assertEqual(tree_calls, [False, True])
        self.assertEqual(terminate_calls, [True])
        self.assertEqual(kill_calls, [True])

    def test_posix_path_uses_killpg(self) -> None:
        if not hasattr(os, "killpg"):
            self.skipTest("os.killpg not available on this platform")

        proc = SimpleNamespace(pid=8888)
        signals: list[int] = []

        def fake_killpg(pid: int, sig: int) -> None:
            self.assertEqual(pid, 8888)
            signals.append(sig)

        with (
            mock.patch.object(ringer.os, "name", "posix"),
            mock.patch.object(ringer.os, "killpg", side_effect=fake_killpg),
        ):
            ringer.terminate_process_group(proc)  # type: ignore[arg-type]
            ringer.kill_process_group(proc)  # type: ignore[arg-type]

        self.assertEqual(signals[0], ringer.signal.SIGTERM)
        # SIGKILL may be absent on some platforms; kill_process_group uses it on POSIX.
        if hasattr(ringer.signal, "SIGKILL"):
            self.assertEqual(signals[1], ringer.signal.SIGKILL)
        else:
            self.assertEqual(len(signals), 1)

    def test_live_child_is_killed(self) -> None:
        """Spawn a sleeper, force-kill the process tree, assert it exits."""

        async def _run() -> None:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            self.assertIsNotNone(proc.pid)
            # Give the OS a moment to register the process.
            await asyncio.sleep(0.2)
            ringer.kill_process_group(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                with self.subTest("fallback terminate"):
                    proc.kill()
                    await proc.wait()
                self.fail("kill_process_group did not reap sleeper within 5s")
            self.assertIsNotNone(proc.returncode)

        asyncio.run(_run())


class ProcessTreeCaptureTests(unittest.TestCase):
    def test_run_capture_uses_tempfile_not_pipe(self) -> None:
        """_run_capture must not use stdout=PIPE (phantom SIGINT on some Windows builds)."""
        seen_kwargs: list[dict] = []

        def fake_run(argv, **kwargs):  # noqa: ANN001, ANN003
            seen_kwargs.append(kwargs)
            stdout = kwargs.get("stdout")
            if hasattr(stdout, "write"):
                stdout.write("image.exe\",\"1234\",\"Session\",\"1\",\"1 K\"\n")
            return SimpleNamespace(returncode=0)

        with mock.patch.object(ringer.subprocess, "run", side_effect=fake_run):
            out = ringer.ProcessTree._run_capture(["tasklist", "/FO", "CSV", "/NH"])

        self.assertIn("1234", out)
        self.assertEqual(len(seen_kwargs), 1)
        self.assertIsNot(seen_kwargs[0].get("stdout"), ringer.subprocess.PIPE)
        self.assertTrue(hasattr(seen_kwargs[0].get("stdout"), "write"))

    def test_read_on_windows_uses_tasklist(self) -> None:
        captured: list[list[str]] = []

        def fake_capture(argv: list[str], timeout: float = 5) -> str:
            captured.append(list(argv))
            return '"python.exe","9999","Console","1","10 K"\n'

        with (
            mock.patch.object(ringer.os, "name", "nt"),
            mock.patch.object(ringer.ProcessTree, "_run_capture", side_effect=fake_capture),
        ):
            children, commands = ringer.ProcessTree.read()

        self.assertEqual(captured[0][:1], ["tasklist"])
        self.assertEqual(commands.get(9999), "python.exe")
        self.assertEqual(children, {})


class WindowsInterruptShieldTests(unittest.TestCase):
    def test_grace_period_swallows_double_phantom(self) -> None:
        """Phantoms often arrive as a pair; both must be ignored during grace."""
        shield = ringer.WindowsInterruptShield(grace_s=10.0, double_tap_s=5.0)
        # Both hits during grace → swallow (True means "handled / no cancel").
        # Rapid pair may share the 80ms debounce; either way must not cancel.
        self.assertTrue(shield._should_swallow())
        self.assertTrue(shield._should_swallow())
        self.assertTrue(shield._armed)
        time.sleep(0.1)
        self.assertTrue(shield._should_swallow())  # still in grace after gap
        self.assertTrue(shield._armed)

    def test_after_grace_double_tap_cancels(self) -> None:
        shield = ringer.WindowsInterruptShield(grace_s=0.0, double_tap_s=5.0)
        shield._started = time.monotonic() - 1.0  # ensure past grace
        self.assertTrue(shield._should_swallow())   # first post-grace
        time.sleep(0.1)  # beyond 80ms debounce so this counts as a new press
        self.assertFalse(shield._should_swallow())  # second → cancel
        self.assertFalse(shield._armed)

    def test_context_manager_noops_off_windows(self) -> None:
        with mock.patch.object(ringer.os, "name", "posix"):
            shield = ringer.WindowsInterruptShield()
            with shield:
                self.assertFalse(shield._installed)


class CheckBashResolutionTests(unittest.TestCase):
    """_resolve_check_bash must prefer real Git Bash over the Store WindowsApps shim."""

    GIT_BASH = r"C:\Program Files\Git\usr\bin\bash.exe"
    WINDOWSAPPS_BASH = r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\bash.EXE"

    def test_windows_prefers_git_bash_over_windowsapps_shim(self) -> None:
        with (
            mock.patch.object(ringer.os, "name", "nt"),
            mock.patch.object(
                ringer.os.path,
                "isfile",
                side_effect=lambda p: p == self.GIT_BASH,
            ),
            mock.patch.object(
                ringer.shutil, "which", return_value=self.WINDOWSAPPS_BASH
            ),
        ):
            self.assertEqual(ringer.Verifier._resolve_check_bash(), self.GIT_BASH)

    def test_windows_falls_back_to_non_shim_which(self) -> None:
        real = r"C:\tools\bash.exe"
        with (
            mock.patch.object(ringer.os, "name", "nt"),
            mock.patch.object(ringer.os.path, "isfile", return_value=False),
            mock.patch.object(ringer.shutil, "which", return_value=real),
        ):
            self.assertEqual(ringer.Verifier._resolve_check_bash(), real)

    def test_windows_rejects_windowsapps_shim_when_no_git_bash(self) -> None:
        with (
            mock.patch.object(ringer.os, "name", "nt"),
            mock.patch.object(ringer.os.path, "isfile", return_value=False),
            mock.patch.object(
                ringer.shutil, "which", return_value=self.WINDOWSAPPS_BASH
            ),
        ):
            self.assertIsNone(ringer.Verifier._resolve_check_bash())

    def test_posix_uses_which(self) -> None:
        with (
            mock.patch.object(ringer.os, "name", "posix"),
            mock.patch.object(ringer.shutil, "which", return_value="/usr/bin/bash"),
        ):
            self.assertEqual(ringer.Verifier._resolve_check_bash(), "/usr/bin/bash")


if __name__ == "__main__":
    unittest.main()
