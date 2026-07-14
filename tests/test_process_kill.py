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


if __name__ == "__main__":
    unittest.main()
