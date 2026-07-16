#!/usr/bin/env python3
"""Offline tests for templates/repo-feature/checks/check_repo_feature.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = ROOT / "templates" / "repo-feature" / "checks" / "check_repo_feature.py"


def load_check_module():
    spec = importlib.util.spec_from_file_location("check_repo_feature", CHECK_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PathNoiseUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_check_module()

    def test_pycache_paths_are_noise(self) -> None:
        for path in (
            "src/__pycache__",
            "src/__pycache__/",
            "tests/__pycache__/cli.cpython-314.pyc",
            "__pycache__/x.pyc",
            ".pytest_cache",
            ".pytest_cache/v/cache/nodeids",
            "pkg/.mypy_cache/3.14/foo.data.json",
            "foo.pyc",
            "src/mod.pyo",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.mod.path_is_noise(path), path)
                self.assertTrue(self.mod.path_allowed(path, []), path)

    def test_real_unowned_paths_not_noise(self) -> None:
        for path in ("secrets.env", "tests/test_foo.py", ".gitignore", "src/cli.py", "data/notes.json"):
            with self.subTest(path=path):
                self.assertFalse(self.mod.path_is_noise(path), path)
                self.assertFalse(self.mod.path_allowed(path, []), path)

    def test_owned_paths_allowed(self) -> None:
        allowed = ["src/task_queue.py", "src/cli.py"]
        self.assertTrue(self.mod.path_allowed("src/task_queue.py", allowed))
        self.assertTrue(self.mod.path_allowed("src/cli.py", allowed))
        self.assertFalse(self.mod.path_allowed("tests/test_cli.py", allowed))

    def test_explicit_allowed_status_extras(self) -> None:
        allowed = ["src/store.py", "data"]
        self.assertTrue(self.mod.path_allowed("data", allowed))
        self.assertTrue(self.mod.path_allowed("data/notes.json", allowed))
        self.assertFalse(self.mod.path_allowed("other/x", allowed))


class CheckScriptIntegrationTests(unittest.TestCase):
    def _init_repo(self, repo: Path) -> None:
        repo.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True, capture_output=True)
        (repo / "src").mkdir()
        (repo / "tests").mkdir()
        owned = repo / "src" / "task_queue.py"
        owned.write_text("class PriorityTaskQueue:\n    pass\n_QUEUE = None\n", encoding="utf-8")
        # tracked empty package so only __pycache__ under tests/ is untracked (not ?? tests/)
        (repo / "tests" / ".gitkeep").write_text("", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)

    def _run_check(
        self,
        *,
        repo: Path,
        notes: Path,
        owned: str = "src/task_queue.py",
        allowed_status: str = "",
        build_command: str = "true" if sys.platform != "win32" else "cmd /c exit 0",
        required_text: str = "class PriorityTaskQueue,_QUEUE",
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(CHECK_PATH),
            "--repo",
            str(repo),
            "--owned",
            owned,
            "--allowed-status",
            allowed_status,
            "--required-paths",
            "src/task_queue.py",
            "--required-text",
            required_text,
            "--build-command",
            build_command,
            "--notes",
            str(notes),
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    def test_pycache_dirty_passes_without_allowed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            self._init_repo(repo)
            # dirty owned edit + pytest noise
            (repo / "src" / "task_queue.py").write_text(
                "class PriorityTaskQueue:\n    pass\n_QUEUE = []\n", encoding="utf-8"
            )
            pyc = repo / "src" / "__pycache__"
            pyc.mkdir()
            (pyc / "task_queue.cpython-314.pyc").write_bytes(b"\0")
            (repo / "tests" / "__pycache__").mkdir()
            (repo / "tests" / "__pycache__" / "x.pyc").write_bytes(b"\0")
            (repo / ".pytest_cache").mkdir()
            (repo / ".pytest_cache" / "v").mkdir()
            notes = root / "notes.md"
            notes.write_text("ok\n", encoding="utf-8")
            # cwd matters for relative notes path handling — pass absolute notes
            proc = self._run_check(repo=repo, notes=notes)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PASS", proc.stdout)

    def test_unowned_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            self._init_repo(repo)
            (repo / "src" / "task_queue.py").write_text(
                "class PriorityTaskQueue:\n    pass\n_QUEUE = []\n", encoding="utf-8"
            )
            (repo / "secrets.env").write_text("x=1\n", encoding="utf-8")
            notes = root / "notes.md"
            notes.write_text("ok\n", encoding="utf-8")
            proc = self._run_check(repo=repo, notes=notes)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("git-status ownership", proc.stdout)
            self.assertIn("secrets.env", proc.stdout)
            self.assertIn("re-run THIS check only", proc.stdout)

    def test_allowed_status_extra_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            self._init_repo(repo)
            (repo / "src" / "task_queue.py").write_text(
                "class PriorityTaskQueue:\n    pass\n_QUEUE = []\n", encoding="utf-8"
            )
            (repo / "data").mkdir()
            (repo / "data" / "out.json").write_text("{}\n", encoding="utf-8")
            notes = root / "notes.md"
            notes.write_text("ok\n", encoding="utf-8")
            proc = self._run_check(repo=repo, notes=notes, allowed_status="data")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_gitignore_not_auto_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            self._init_repo(repo)
            (repo / "src" / "task_queue.py").write_text(
                "class PriorityTaskQueue:\n    pass\n_QUEUE = []\n", encoding="utf-8"
            )
            (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            notes = root / "notes.md"
            notes.write_text("ok\n", encoding="utf-8")
            proc = self._run_check(repo=repo, notes=notes)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn(".gitignore", proc.stdout)


if __name__ == "__main__":
    unittest.main()
