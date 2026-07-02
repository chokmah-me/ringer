#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable


CODEX_BIN = "/opt/homebrew/bin/codex"
DEFAULT_TIMEOUT_S = 900
CHECK_TIMEOUT_S = 60
RUNS_DIR = Path.home() / ".swarm" / "runs"
JSONL_FALLBACK_PATH = Path.home() / "fleet" / "swarm" / "runs.jsonl"
SUPABASE_ENV_PATH = Path.home() / ".claude" / "data" / "supabase.env"
WORKER_ENGINE = "codex gpt-5.5"
SHEPHERD_MODEL = "none (swarm.py)"
VERIFY_METHOD = "executed-check"
SWARM_HUD_APP_PATH = Path("/Users/jonathanedwards/fleet/swarm/SwarmHUD.app")


@dataclass(frozen=True)
class TaskSpec:
    key: str
    spec: str
    check: str
    expect_files: tuple[str, ...] = ()
    timeout_s: int = DEFAULT_TIMEOUT_S
    full_access: bool = False

    @classmethod
    def from_obj(cls, obj: dict[str, Any]) -> "TaskSpec":
        key = str(obj.get("key", "")).strip()
        spec = str(obj.get("spec", ""))
        check = str(obj.get("check", ""))
        if not key:
            raise ValueError("task key is required")
        if not spec:
            raise ValueError(f"task {key}: spec is required")
        if not check:
            raise ValueError(f"task {key}: check is required")
        expect_files = obj.get("expect_files", [])
        if not isinstance(expect_files, list):
            raise ValueError(f"task {key}: expect_files must be a list")
        timeout_s = int(obj.get("timeout_s", DEFAULT_TIMEOUT_S))
        if timeout_s <= 0:
            raise ValueError(f"task {key}: timeout_s must be positive")
        return cls(
            key=key,
            spec=spec,
            check=check,
            expect_files=tuple(str(item) for item in expect_files),
            timeout_s=timeout_s,
            full_access=bool(obj.get("full_access", False)),
        )


@dataclass(frozen=True)
class Manifest:
    run_name: str
    workdir: Path
    max_parallel: int
    worktrees: bool
    repo: Path | None
    tasks: tuple[TaskSpec, ...]
    source_path: Path | None = None

    @classmethod
    def from_path(cls, path: Path) -> "Manifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest root must be a JSON object")
        manifest = cls.from_obj(data)
        return cls(
            run_name=manifest.run_name,
            workdir=manifest.workdir,
            max_parallel=manifest.max_parallel,
            worktrees=manifest.worktrees,
            repo=manifest.repo,
            tasks=manifest.tasks,
            source_path=path,
        )

    @classmethod
    def from_obj(cls, obj: dict[str, Any]) -> "Manifest":
        run_name = str(obj.get("run_name", "")).strip()
        if not run_name:
            raise ValueError("run_name is required")
        workdir_raw = obj.get("workdir")
        if not workdir_raw:
            raise ValueError("workdir is required")
        workdir = Path(str(workdir_raw)).expanduser().resolve()
        max_parallel = int(obj.get("max_parallel", 1))
        if max_parallel <= 0:
            raise ValueError("max_parallel must be positive")
        repo_raw = obj.get("repo")
        repo = Path(str(repo_raw)).expanduser().resolve() if repo_raw else None
        tasks_raw = obj.get("tasks")
        if not isinstance(tasks_raw, list) or not tasks_raw:
            raise ValueError("tasks must be a non-empty list")
        tasks = tuple(TaskSpec.from_obj(task) for task in tasks_raw)
        keys = [task.key for task in tasks]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"duplicate task keys: {', '.join(duplicates)}")
        return cls(
            run_name=run_name,
            workdir=workdir,
            max_parallel=max_parallel,
            worktrees=bool(obj.get("worktrees", False)),
            repo=repo,
            tasks=tasks,
        )

    def with_max_parallel(self, value: int | None) -> "Manifest":
        if value is None:
            return self
        if value <= 0:
            raise ValueError("--max-parallel must be positive")
        return Manifest(
            run_name=self.run_name,
            workdir=self.workdir,
            max_parallel=value,
            worktrees=self.worktrees,
            repo=self.repo,
            tasks=self.tasks,
            source_path=self.source_path,
        )


@dataclass
class TaskRuntime:
    task: TaskSpec
    taskdir: Path
    status: str = "queued"
    spec_short: str = ""
    attempts: int = 0
    started_at_monotonic: float | None = None
    ended_at_monotonic: float | None = None
    worker_pid: int | None = None
    tokens: int | None = None
    final_verdict: str | None = None

    def elapsed_s(self, now: float) -> float:
        if self.started_at_monotonic is None:
            return 0.0
        end = self.ended_at_monotonic if self.ended_at_monotonic is not None else now
        return max(0.0, end - self.started_at_monotonic)


@dataclass(frozen=True)
class WorkerResult:
    returncode: int | None
    timed_out: bool
    tokens: int | None
    error: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    check_returncode: int | None
    check_timed_out: bool
    raw_output_excerpt: str
    missing_files: tuple[str, ...] = ()


class ProcessTree:
    @staticmethod
    def read() -> tuple[dict[int, list[int]], dict[int, str]]:
        try:
            proc = subprocess.run(
                ["ps", "-eo", "pid=,ppid=,args="],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except Exception:
            return {}, {}
        children: dict[int, list[int]] = {}
        commands: dict[int, str] = {}
        for line in proc.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except ValueError:
                continue
            command = parts[2] if len(parts) > 2 else ""
            children.setdefault(ppid, []).append(pid)
            commands[pid] = command
        return children, commands

    @staticmethod
    def count_codex_descendants(
        root_pid: int | None, children: dict[int, list[int]], commands: dict[int, str]
    ) -> int:
        if root_pid is None:
            return 0
        count = 0
        stack = list(children.get(root_pid, []))
        while stack:
            pid = stack.pop()
            command = commands.get(pid, "")
            if "codex" in Path(command.split()[0]).name.lower() if command else False:
                count += 1
            stack.extend(children.get(pid, []))
        return count


class StateWriter:
    def __init__(
        self,
        run_id: str,
        run_name: str,
        identity: str,
        started_at: datetime,
        runtimes: list[TaskRuntime],
        lock: threading.RLock,
        path: Path | None = None,
    ) -> None:
        self.run_id = run_id
        self.run_name = run_name
        self.identity = identity
        self.started_at = started_at
        self.runtimes = runtimes
        self.lock = lock
        self.path = path or (RUNS_DIR / f"{run_id}.json")
        self.pid = os.getpid()
        self.port: int | None = None
        self.finished = False
        self.summary: dict[str, int] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()
        self.flush()
        self._thread = threading.Thread(target=self._loop, name="swarm-state-writer", daemon=True)
        self._thread.start()

    def set_port(self, port: int | None) -> None:
        self.port = port
        self.flush()

    def finish(self) -> None:
        self.finished = True
        self.summary = self.build_summary()
        self.flush()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.flush()

    def flush(self) -> None:
        state = self.snapshot()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        children, commands = ProcessTree.read()
        with self.lock:
            tasks = []
            for runtime in self.runtimes:
                log_tail = tail_lines(runtime.taskdir / "worker.log", line_count=3)
                tasks.append(
                    {
                        "key": runtime.task.key,
                        "status": runtime.status,
                        "spec_short": runtime.spec_short,
                        "elapsed_s": round(runtime.elapsed_s(now), 1),
                        "tokens": runtime.tokens,
                        "children": ProcessTree.count_codex_descendants(
                            runtime.worker_pid, children, commands
                        ),
                        "log_tail": log_tail,
                    }
                )
            pass_count = sum(1 for item in tasks if item["status"] == "pass")
            fail_count = sum(1 for item in tasks if item["status"] == "fail")
            running_count = sum(
                1 for item in tasks if item["status"] in {"running", "verifying", "retrying"}
            )
            totals = {
                "running": running_count,
                "done": pass_count + fail_count,
                "pass": pass_count,
                "fail": fail_count,
                "tokens": sum(int(item["tokens"] or 0) for item in tasks),
            }
            return {
                "run_id": self.run_id,
                "run_name": self.run_name,
                "identity": self.identity,
                "pid": self.pid,
                "port": self.port,
                "finished": self.finished,
                "summary": self.summary if self.finished else None,
                "started_at": self.started_at.isoformat(),
                "tasks": tasks,
                "totals": totals,
            }

    def build_summary(self) -> dict[str, int]:
        with self.lock:
            return {
                "pass": sum(1 for runtime in self.runtimes if runtime.status == "pass"),
                "fail": sum(1 for runtime in self.runtimes if runtime.status == "fail"),
                "tokens": sum(int(runtime.tokens or 0) for runtime in self.runtimes),
            }

    def _loop(self) -> None:
        while not self._stop.wait(1.0):
            try:
                self.flush()
            except Exception as exc:
                print(f"state writer error: {exc}", file=sys.stderr)


class Dashboard:
    def __init__(
        self,
        state_path: Path,
        preferred_port: int = 8787,
        force_browser: bool = False,
    ) -> None:
        self.state_path = state_path
        self.preferred_port = preferred_port
        self.force_browser = force_browser
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port: int | None = None

    def start(self) -> int:
        state_path = self.state_path

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urllib.parse.urlparse(self.path).path
                if path == "/":
                    body = DASHBOARD_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == "/state.json":
                    try:
                        body = state_path.read_bytes()
                    except FileNotFoundError:
                        body = b'{"run_name":"swarm","started_at":"","tasks":[],"totals":{"running":0,"done":0,"pass":0,"fail":0,"tokens":0}}'
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        last_error: OSError | None = None
        for port in range(self.preferred_port, self.preferred_port + 50):
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            except OSError as exc:
                last_error = exc
                continue
            self.port = port
            break
        if self.httpd is None or self.port is None:
            raise RuntimeError(f"could not start dashboard: {last_error}")
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="swarm-dashboard", daemon=True)
        self.thread.start()
        url = f"http://localhost:{self.port}"
        try:
            if not self.force_browser and SWARM_HUD_APP_PATH.exists():
                subprocess.Popen(
                    ["open", "-a", str(SWARM_HUD_APP_PATH)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        print(f"Dashboard: {url}")
        return self.port

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


class EvalLogger:
    def __init__(self) -> None:
        self._conn: Any | None = None
        self._fallback_path = JSONL_FALLBACK_PATH
        self._fallback_reason: str | None = None
        self._connect()

    def log_attempt(self, row: dict[str, Any]) -> None:
        db_row = dict(row)
        if self._conn is not None:
            try:
                self._conn.execute(
                    """
                    INSERT INTO swarm_runs (
                        run_id, pattern, task_key, spec, worker_engine, shepherd_model,
                        verify_method, verdict, duration_ms, worker_tokens, notes, orchestrator
                    )
                    VALUES (
                        %(run_id)s, %(pattern)s, %(task_key)s, %(spec)s, %(worker_engine)s,
                        %(shepherd_model)s, %(verify_method)s, %(verdict)s, %(duration_ms)s,
                        %(worker_tokens)s, %(notes)s, %(orchestrator)s
                    )
                    """,
                    db_row,
                )
                return
            except Exception as exc:
                self._fallback_reason = f"Supabase insert failed: {exc}"
                self._close_conn()
        self._write_jsonl(db_row)

    def close(self) -> None:
        self._close_conn()

    def _connect(self) -> None:
        try:
            import psycopg  # type: ignore[import-not-found]
        except Exception as exc:
            self._fallback_reason = f"psycopg import failed: {exc}"
            return
        creds = parse_supabase_env(SUPABASE_ENV_PATH)
        required = [
            "SUPABASE_DB_HOST",
            "SUPABASE_DB_PORT",
            "SUPABASE_DB_USER",
            "SUPABASE_DB_PASSWORD",
            "SUPABASE_DB_NAME",
        ]
        missing = [key for key in required if not creds.get(key)]
        if missing:
            self._fallback_reason = f"missing Supabase env keys: {', '.join(missing)}"
            return
        try:
            self._conn = psycopg.connect(
                host=creds["SUPABASE_DB_HOST"],
                port=int(creds["SUPABASE_DB_PORT"]),
                user=creds["SUPABASE_DB_USER"],
                password=creds["SUPABASE_DB_PASSWORD"],
                dbname=creds["SUPABASE_DB_NAME"],
                autocommit=True,
                connect_timeout=5,
            )
        except Exception as exc:
            self._fallback_reason = f"Supabase connect failed: {exc}"

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(row)
        payload["logged_at"] = datetime.now(timezone.utc).isoformat()
        payload["log_sink"] = "jsonl"
        payload["fallback_reason"] = self._fallback_reason
        with self._fallback_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")

    def _close_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


class Verifier:
    async def verify(self, task: TaskSpec, taskdir: Path) -> VerifyResult:
        missing_files = tuple(
            rel for rel in task.expect_files if not self._is_nonempty_file(taskdir / rel)
        )
        check_returncode, check_timed_out, output = await self._run_check(task.check, taskdir)
        ok = not missing_files and not check_timed_out and check_returncode == 0
        return VerifyResult(
            ok=ok,
            check_returncode=check_returncode,
            check_timed_out=check_timed_out,
            raw_output_excerpt=output[:2000],
            missing_files=missing_files,
        )

    @staticmethod
    def _is_nonempty_file(path: Path) -> bool:
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    @staticmethod
    async def _run_check(command: str, cwd: Path) -> tuple[int | None, bool, str]:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CHECK_TIMEOUT_S)
        except asyncio.TimeoutError:
            timed_out = True
            terminate_process_group(proc)
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                kill_process_group(proc)
                stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if timed_out:
            output += f"\n[swarm.py] check timed out after {CHECK_TIMEOUT_S}s\n"
        return proc.returncode, timed_out, output


class SwarmRunner:
    def __init__(
        self,
        manifest: Manifest,
        identity: str,
        dashboard_enabled: bool = True,
        force_browser: bool = False,
    ) -> None:
        self.manifest = manifest
        self.identity = identity
        self.dashboard_enabled = dashboard_enabled
        self.run_id = build_run_id(manifest.run_name)
        self.started_at = datetime.now(timezone.utc)
        self.lock = threading.RLock()
        self.runtimes = [
            TaskRuntime(
                task=task,
                taskdir=self._taskdir(task),
                spec_short=shorten(task.spec, 120),
            )
            for task in manifest.tasks
        ]
        self.state_writer = StateWriter(
            self.run_id,
            manifest.run_name,
            identity,
            self.started_at,
            self.runtimes,
            self.lock,
        )
        self.dashboard = (
            Dashboard(state_path=self.state_writer.path, force_browser=force_browser)
            if dashboard_enabled
            else None
        )
        self.logger = EvalLogger()
        self.verifier = Verifier()
        self.semaphore = asyncio.Semaphore(manifest.max_parallel)
        self.active_processes: dict[int, asyncio.subprocess.Process] = {}

    async def run(self) -> int:
        self.manifest.workdir.mkdir(parents=True, exist_ok=True)
        final_state = False
        try:
            self.state_writer.start()
            if self.dashboard is not None:
                self.state_writer.set_port(self.dashboard.start())
            await asyncio.gather(*(self._run_task(runtime) for runtime in self.runtimes))
            final_state = True
            return 0 if all(runtime.status == "pass" for runtime in self.runtimes) else 1
        except asyncio.CancelledError:
            await self.kill_all_workers()
            with self.lock:
                now = time.monotonic()
                for runtime in self.runtimes:
                    if runtime.status not in {"pass", "fail"}:
                        runtime.status = "fail"
                        runtime.final_verdict = "ERROR"
                        runtime.ended_at_monotonic = runtime.ended_at_monotonic or now
            self.state_writer.flush()
            final_state = True
            raise
        finally:
            if final_state:
                self.state_writer.finish()
            self.state_writer.stop()
            if self.dashboard is not None:
                self.dashboard.stop()
            self.logger.close()
            print_summary(self.run_id, self.runtimes)

    async def kill_all_workers(self) -> None:
        procs = list(self.active_processes.values())
        for proc in procs:
            if proc.returncode is None:
                terminate_process_group(proc)
        if procs:
            await asyncio.sleep(1)
        for proc in procs:
            if proc.returncode is None:
                kill_process_group(proc)

    async def _run_task(self, runtime: TaskRuntime) -> None:
        async with self.semaphore:
            with self.lock:
                runtime.started_at_monotonic = time.monotonic()
            prepared, prepare_error = await self._prepare_taskdir(runtime)
            if not prepared:
                await self._record_prepare_error(runtime, prepare_error or "taskdir preparation failed")
                return
            current_spec = runtime.task.spec
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                retrying = attempt > 1
                with self.lock:
                    runtime.attempts = attempt
                    runtime.status = "retrying" if retrying else "running"
                attempt_started = time.monotonic()
                worker = await self._run_worker(runtime, current_spec, attempt)
                with self.lock:
                    runtime.worker_pid = None
                    runtime.status = "verifying"
                    if worker.tokens is not None:
                        runtime.tokens = (runtime.tokens or 0) + worker.tokens
                verify = await self.verifier.verify(runtime.task, runtime.taskdir)
                verdict = verdict_for(worker, verify)
                duration_ms = int((time.monotonic() - attempt_started) * 1000)
                self._log_attempt(runtime, current_spec, retrying, worker, verify, verdict, duration_ms)
                if verdict == "PASS":
                    with self.lock:
                        runtime.status = "pass"
                        runtime.final_verdict = verdict
                        runtime.ended_at_monotonic = time.monotonic()
                    await self._cleanup_worktree_on_pass(runtime)
                    return
                if attempt < max_attempts and verdict in {"FAIL", "TIMEOUT"}:
                    failure_context = build_failure_context(runtime.taskdir, verify.raw_output_excerpt)
                    current_spec = (
                        f"{runtime.task.spec}\n\n"
                        f"Previous attempt failed: {failure_context}. Fix it."
                    )
                    continue
                with self.lock:
                    runtime.status = "fail"
                    runtime.final_verdict = verdict
                    runtime.ended_at_monotonic = time.monotonic()
                return

    async def _prepare_taskdir(self, runtime: TaskRuntime) -> tuple[bool, str | None]:
        taskdir = runtime.taskdir
        if self.manifest.worktrees and self.manifest.repo is not None:
            taskdir.parent.mkdir(parents=True, exist_ok=True)
            if taskdir.exists():
                return False, f"worktree taskdir already exists: {taskdir}"
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(self.manifest.repo),
                "worktree",
                "add",
                str(taskdir),
                "HEAD",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                message = stdout.decode("utf-8", errors="replace")
                append_text(taskdir / "worker.log", f"[swarm.py] git worktree add failed:\n{message}\n")
                return False, message.strip() or "git worktree add failed"
            return True, None
        taskdir.mkdir(parents=True, exist_ok=True)
        return True, None

    async def _cleanup_worktree_on_pass(self, runtime: TaskRuntime) -> None:
        if not (self.manifest.worktrees and self.manifest.repo is not None):
            return
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.manifest.repo),
            "worktree",
            "remove",
            "--force",
            str(runtime.taskdir),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            message = stdout.decode("utf-8", errors="replace")
            append_text(runtime.taskdir / "worker.log", f"[swarm.py] git worktree remove failed:\n{message}\n")

    async def _record_prepare_error(self, runtime: TaskRuntime, error: str) -> None:
        with self.lock:
            runtime.attempts = 1
            runtime.status = "fail"
            runtime.final_verdict = "ERROR"
            runtime.ended_at_monotonic = time.monotonic()
        verify = VerifyResult(
            ok=False,
            check_returncode=None,
            check_timed_out=False,
            raw_output_excerpt="",
        )
        worker = WorkerResult(returncode=None, timed_out=False, tokens=None, error=error)
        self._log_attempt(runtime, runtime.task.spec, False, worker, verify, "ERROR", 0)

    async def _run_worker(self, runtime: TaskRuntime, spec: str, attempt: int) -> WorkerResult:
        log_path = runtime.taskdir / "worker.log"
        cmd = [CODEX_BIN, "exec", "--skip-git-repo-check"]
        if runtime.task.full_access:
            # Nested subbies need network: children run under this worker's sandbox.
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            # Never rely on the default sandbox: it resolves to read-only in
            # untrusted dirs (e.g. /tmp), which blocks all artifact writes.
            cmd += ["--sandbox", "workspace-write"]
        cmd += ["-C", str(runtime.taskdir), spec]
        append_text(
            log_path,
            "\n"
            f"[swarm.py] attempt {attempt} started {datetime.now(timezone.utc).isoformat()}\n"
            f"[swarm.py] command: {shell_command_for_display(cmd)} < /dev/null\n",
        )
        capture = RollingBytes(max_bytes=1_000_000)
        try:
            log_fh = log_path.open("ab")
        except OSError as exc:
            return WorkerResult(returncode=None, timed_out=False, tokens=None, error=str(exc))
        async with AsyncFileCloser(log_fh):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(runtime.taskdir),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception as exc:
                message = f"[swarm.py] worker spawn failed: {exc}\n"
                log_fh.write(message.encode("utf-8", errors="replace"))
                log_fh.flush()
                return WorkerResult(returncode=None, timed_out=False, tokens=None, error=str(exc))
            with self.lock:
                runtime.worker_pid = proc.pid
            self.active_processes[proc.pid] = proc
            reader = asyncio.create_task(self._tee_stream(proc, log_fh, capture))
            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout=runtime.task.timeout_s)
            except asyncio.TimeoutError:
                timed_out = True
                terminate_process_group(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    kill_process_group(proc)
                    await proc.wait()
            try:
                await asyncio.wait_for(reader, timeout=5)
            except asyncio.TimeoutError:
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader
            self.active_processes.pop(proc.pid, None)
        output_tail = capture.text()
        tokens = parse_token_count(output_tail)
        if timed_out:
            append_text(log_path, f"\n[swarm.py] worker timed out after {runtime.task.timeout_s}s\n")
        append_text(log_path, f"[swarm.py] attempt {attempt} exited rc={proc.returncode}\n")
        return WorkerResult(returncode=proc.returncode, timed_out=timed_out, tokens=tokens)

    async def _tee_stream(
        self,
        proc: asyncio.subprocess.Process,
        log_fh: Any,
        capture: "RollingBytes",
    ) -> None:
        if proc.stdout is None:
            return
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                return
            log_fh.write(chunk)
            log_fh.flush()
            capture.extend(chunk)
            try:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            except Exception:
                pass

    def _log_attempt(
        self,
        runtime: TaskRuntime,
        spec: str,
        retrying: bool,
        worker: WorkerResult,
        verify: VerifyResult,
        verdict: str,
        duration_ms: int,
    ) -> None:
        notes_parts = [
            f"retry={'true' if retrying else 'false'}",
            f"worker_returncode={worker.returncode}",
        ]
        if worker.error:
            notes_parts.append(f"worker_error={worker.error}")
        if verify.missing_files:
            notes_parts.append(f"missing_expect_files={json.dumps(list(verify.missing_files))}")
        notes_parts.append("raw_check_output_first_2000_chars:")
        notes_parts.append(verify.raw_output_excerpt)
        self.logger.log_attempt(
            {
                "run_id": self.run_id,
                "pattern": "swarm-py",
                "task_key": runtime.task.key,
                "spec": spec[:500],
                "worker_engine": WORKER_ENGINE,
                "shepherd_model": SHEPHERD_MODEL,
                "verify_method": VERIFY_METHOD,
                "verdict": verdict,
                "duration_ms": duration_ms,
                "worker_tokens": worker.tokens,
                "notes": "\n".join(notes_parts),
                "orchestrator": self.identity,
            }
        )

    def _taskdir(self, task: TaskSpec) -> Path:
        taskdir = (self.manifest.workdir / task.key).resolve()
        workdir = self.manifest.workdir.resolve()
        if taskdir != workdir and workdir not in taskdir.parents:
            raise ValueError(f"task key escapes workdir: {task.key}")
        return taskdir


class RollingBytes:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.data = bytearray()

    def extend(self, chunk: bytes) -> None:
        self.data.extend(chunk)
        overflow = len(self.data) - self.max_bytes
        if overflow > 0:
            del self.data[:overflow]

    def text(self) -> str:
        return bytes(self.data).decode("utf-8", errors="replace")


class AsyncFileCloser:
    def __init__(self, fh: Any) -> None:
        self.fh = fh

    async def __aenter__(self) -> Any:
        return self.fh

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.fh.close()


def verdict_for(worker: WorkerResult, verify: VerifyResult) -> str:
    if worker.error:
        return "ERROR"
    if worker.timed_out or verify.check_timed_out:
        return "TIMEOUT"
    if verify.ok:
        return "PASS"
    return "FAIL"


def build_run_id(run_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_name.strip()).strip("-")
    # pid suffix: same-second launches of the same run_name must not collide
    # (concurrent swarms would otherwise share a state file and eval run_id).
    return f"{safe_name or 'swarm'}-{stamp}-p{os.getpid()}"


def resolve_identity(value: str | None) -> str:
    for candidate in (value, os.environ.get("FLEET_IDENTITY"), os.environ.get("SWARM_IDENTITY")):
        if candidate and candidate.strip():
            return candidate.strip()
    return socket.gethostname().split(".", 1)[0] or "swarm"


def parse_supabase_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_token_count(text: str) -> int | None:
    matches = re.findall(r"tokens\s+used\s*:?\s*([0-9][0-9,]*)", text, flags=re.IGNORECASE)
    if not matches:
        matches = re.findall(
            r"tokens\s+used\s*\r?\n\s*([0-9][0-9,]*)",
            text,
            flags=re.IGNORECASE,
        )
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def tail_lines(path: Path, line_count: int) -> list[str]:
    if line_count <= 0 or not path.exists():
        return []
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            data = fh.read()
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-line_count:]


def tail_text(path: Path, max_bytes: int = 6000, line_count: int = 40) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except OSError:
        return ""
    return "\n".join(data.decode("utf-8", errors="replace").splitlines()[-line_count:])


def build_failure_context(taskdir: Path, raw_check_output: str) -> str:
    worker_tail = tail_text(taskdir / "worker.log")
    context = f"{worker_tail}\n{raw_check_output}".strip()
    if len(context) > 6000:
        return context[-6000:]
    return context


def shorten(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)] + "..."


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


def terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass


def kill_process_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def shell_command_for_display(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def dry_run(manifest: Manifest, identity: str, dashboard_enabled: bool, force_browser: bool) -> None:
    print("DRY RUN: no codex workers will be spawned.")
    print(f"Run: {manifest.run_name}")
    print(f"Identity: {identity}")
    print(f"Workdir: {manifest.workdir}")
    print(f"Max parallel: {manifest.max_parallel}")
    print(f"Worktrees: {manifest.worktrees} repo={manifest.repo}")
    print(f"Dashboard: {'on' if dashboard_enabled else 'off'}")
    if dashboard_enabled:
        mode = "browser" if force_browser else "SwarmHUD app when available, browser fallback"
        print(f"Dashboard opener: {mode}")
    print("Tasks:")
    for task in manifest.tasks:
        taskdir = (manifest.workdir / task.key).resolve()
        cmd = [CODEX_BIN, "exec", "--skip-git-repo-check", "-C", str(taskdir), task.spec]
        print(f"  - {task.key}")
        print(f"    dir: {taskdir}")
        print(f"    timeout_s: {task.timeout_s}")
        print(f"    expect_files: {list(task.expect_files)}")
        print(f"    check: {task.check}")
        print(f"    command: {shell_command_for_display(cmd)} < /dev/null")


def print_summary(run_id: str, runtimes: list[TaskRuntime]) -> None:
    print("\nSummary")
    print(f"run_id: {run_id}")
    header = f"{'task':<24} {'status':<8} {'verdict':<8} {'attempts':>8} {'tokens':>10} {'elapsed_s':>10}"
    print(header)
    print("-" * len(header))
    now = time.monotonic()
    for runtime in runtimes:
        tokens = "" if runtime.tokens is None else str(runtime.tokens)
        print(
            f"{runtime.task.key:<24} {runtime.status:<8} "
            f"{(runtime.final_verdict or ''):<8} {runtime.attempts:>8} "
            f"{tokens:>10} {runtime.elapsed_s(now):>10.1f}"
        )


def create_demo_manifest() -> Path:
    root = Path(tempfile.mkdtemp(prefix="swarm-demo-"))
    workdir = root / "work"
    manifest = {
        "run_name": "swarm-demo",
        "workdir": str(workdir),
        "max_parallel": 3,
        "worktrees": False,
        "repo": None,
        "tasks": [
            {
                "key": "alpha",
                "spec": "Create alpha.txt containing exactly: alpha ready",
                "check": "test \"$(cat alpha.txt 2>/dev/null)\" = \"alpha ready\"",
                "expect_files": ["alpha.txt"],
            },
            {
                "key": "bravo",
                "spec": "Create bravo.txt containing exactly: bravo ready",
                "check": "test \"$(cat bravo.txt 2>/dev/null)\" = \"bravo ready\"",
                "expect_files": ["bravo.txt"],
            },
            {
                "key": "charlie",
                "spec": "Create charlie.txt containing exactly: charlie ready",
                "check": "test \"$(cat charlie.txt 2>/dev/null)\" = \"charlie ready\"",
                "expect_files": ["charlie.txt"],
            },
        ],
    }
    path = root / "swarm.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


async def run_manifest(
    manifest: Manifest,
    identity: str,
    dashboard_enabled: bool,
    force_browser: bool,
) -> int:
    runner = SwarmRunner(
        manifest,
        identity=identity,
        dashboard_enabled=dashboard_enabled,
        force_browser=force_browser,
    )
    return await runner.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarm.py",
        description=(
            "Deterministic Codex swarm orchestrator. Runs manifest tasks in parallel, "
            "verifies artifacts with executed checks, retries failures once, logs eval rows, "
            "and serves a live dashboard."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a swarm manifest")
    run_parser.add_argument("manifest", type=Path, help="path to swarm.json")
    run_parser.add_argument("--max-parallel", type=int, help="override manifest max_parallel")
    run_parser.add_argument("--identity", help="orchestrator identity for HUD state and swarm_runs")
    run_parser.add_argument("--no-dashboard", action="store_true", help="disable live dashboard")
    run_parser.add_argument("--browser", action="store_true", help="open the dashboard in the browser instead of SwarmHUD")
    run_parser.add_argument("--dry-run", action="store_true", help="print the plan without spawning codex")

    demo_parser = subparsers.add_parser("demo", help="generate and run a 3-task toy manifest in /tmp")
    demo_parser.add_argument("--max-parallel", type=int, help="override demo max_parallel")
    demo_parser.add_argument("--identity", help="orchestrator identity for HUD state and swarm_runs")
    demo_parser.add_argument("--no-dashboard", action="store_true", help="disable live dashboard")
    demo_parser.add_argument("--browser", action="store_true", help="open the dashboard in the browser instead of SwarmHUD")
    demo_parser.add_argument("--dry-run", action="store_true", help="print the demo plan without spawning codex")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            manifest_path = create_demo_manifest()
            print(f"Demo manifest: {manifest_path}")
        else:
            manifest_path = args.manifest
        manifest = Manifest.from_path(manifest_path).with_max_parallel(args.max_parallel)
        identity = resolve_identity(args.identity)
        dashboard_enabled = not args.no_dashboard
        if args.dry_run:
            dry_run(
                manifest,
                identity=identity,
                dashboard_enabled=dashboard_enabled,
                force_browser=args.browser,
            )
            return 0
        return asyncio.run(
            run_manifest(
                manifest,
                identity=identity,
                dashboard_enabled=dashboard_enabled,
                force_browser=args.browser,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"swarm.py: error: {exc}", file=sys.stderr)
        return 2


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>swarm mission control</title>
<style>
:root {
  color-scheme: dark;
  --bg: #080a0f;
  --panel: #111722;
  --panel-2: #151d2b;
  --line: rgba(255,255,255,.12);
  --text: #eef4ff;
  --muted: #8f9db2;
  --cyan: #28d7ff;
  --amber: #ffbe45;
  --green: #49e27d;
  --red: #ff5468;
  --gray: #778195;
}
* { box-sizing: border-box; }
html, body { min-height: 100%; }
body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at 50% -20%, rgba(40,215,255,.16), transparent 34rem),
    linear-gradient(180deg, #080a0f 0%, #0d1119 60%, #080a0f 100%);
  color: var(--text);
  overflow-x: hidden;
}
body:before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.9), transparent);
}
.shell { width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 96px; }
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 22px;
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pulse {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 0 0 rgba(40,215,255,.7), 0 0 28px rgba(40,215,255,.9);
  animation: pulse 1.4s infinite;
  flex: 0 0 auto;
}
h1 {
  margin: 0;
  font-size: clamp(22px, 3vw, 42px);
  line-height: 1;
  letter-spacing: 0;
  text-transform: uppercase;
  overflow-wrap: anywhere;
}
.meta {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  text-align: right;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  padding-top: 18px;
}
.card {
  position: relative;
  min-height: 210px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(21,29,43,.92), rgba(11,15,23,.96));
  overflow: hidden;
  transition: border-color .25s ease, transform .25s ease, box-shadow .25s ease;
}
.card.running, .card.retrying {
  border-color: rgba(40,215,255,.45);
  box-shadow: 0 0 38px rgba(40,215,255,.12);
}
.card.pass { border-color: rgba(73,226,125,.46); }
.card.fail { border-color: rgba(255,84,104,.54); }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.key {
  min-width: 0;
  font-size: 19px;
  font-weight: 800;
  overflow-wrap: anywhere;
}
.chip {
  flex: 0 0 auto;
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  color: #080a0f;
  background: var(--gray);
  text-transform: uppercase;
}
.chip.running {
  background: var(--cyan);
  animation: glow 1.2s infinite alternate;
}
.chip.retrying {
  background: var(--cyan);
  animation: glow 650ms infinite alternate;
}
.chip.verifying { background: var(--amber); }
.chip.pass { background: var(--green); }
.chip.fail { background: var(--red); }
.spec {
  margin: 12px 0 16px;
  color: #c7d2e5;
  font-size: 13px;
  line-height: 1.35;
  min-height: 36px;
  overflow-wrap: anywhere;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.metric {
  border: 1px solid rgba(255,255,255,.08);
  background: rgba(255,255,255,.035);
  border-radius: 8px;
  padding: 8px;
  min-width: 0;
}
.label {
  color: var(--muted);
  text-transform: uppercase;
  font-size: 10px;
  font-weight: 800;
  margin-bottom: 4px;
}
.value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.subbies {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 24px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(40,215,255,.34);
  background: rgba(40,215,255,.1);
  color: #b9f3ff;
  font-size: 12px;
  font-weight: 800;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity .2s ease, transform .2s ease;
}
.subbies.on { opacity: 1; transform: translateY(0); }
.log {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 16px;
  min-height: 38px;
  max-height: 38px;
  overflow: hidden;
  color: #d8e3f4;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.35;
  opacity: .72;
  transition: opacity .25s ease, transform .25s ease;
}
.log.flash { opacity: 1; transform: translateY(-2px); }
.shimmer {
  position: absolute;
  inset: auto 0 0 0;
  height: 3px;
  opacity: 0;
  background: linear-gradient(90deg, transparent, rgba(40,215,255,.92), transparent);
  transform: translateX(-100%);
  animation: sweep 1.3s linear infinite;
  transition: opacity .2s ease;
}
.footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  border-top: 1px solid var(--line);
  background: rgba(8,10,15,.9);
  backdrop-filter: blur(14px);
}
.footer-inner {
  width: min(1440px, calc(100% - 32px));
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #cdd8ea;
  font-size: 13px;
  flex-wrap: wrap;
}
.totals { display: flex; gap: 14px; flex-wrap: wrap; }
.totals b { color: var(--text); }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(40,215,255,.62), 0 0 28px rgba(40,215,255,.9); }
  70% { box-shadow: 0 0 0 14px rgba(40,215,255,0), 0 0 28px rgba(40,215,255,.9); }
  100% { box-shadow: 0 0 0 0 rgba(40,215,255,0), 0 0 28px rgba(40,215,255,.9); }
}
@keyframes glow {
  from { box-shadow: 0 0 8px rgba(40,215,255,.2); }
  to { box-shadow: 0 0 20px rgba(40,215,255,.85); }
}
@keyframes sweep {
  to { transform: translateX(100%); }
}
@media (max-width: 640px) {
  .shell { width: min(100% - 20px, 640px); padding-top: 12px; }
  .topbar { align-items: flex-start; flex-direction: column; }
  .grid { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: 1fr 1fr; }
}
</style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <div class="brand"><span class="pulse"></span><h1 id="runName">swarm</h1></div>
    <div class="meta"><span id="startedAt">booting</span><span id="topElapsed">00:00</span></div>
  </header>
  <main id="grid" class="grid"></main>
</div>
<footer class="footer">
  <div class="footer-inner">
    <div class="totals">
      <span>running <b id="totalRunning">0</b></span>
      <span>done <b id="totalDone">0</b></span>
      <span>pass <b id="totalPass">0</b></span>
      <span>fail <b id="totalFail">0</b></span>
    </div>
    <div>token burn <b id="totalTokens">0</b> / elapsed <b id="elapsed">00:00</b></div>
  </div>
</footer>
<script>
const grid = document.getElementById("grid");
const cards = new Map();
let startedAt = null;
let displayedTokens = 0;

function fmtElapsed(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function makeCard(key) {
  const card = document.createElement("section");
  card.className = "card queued";
  card.innerHTML = `
    <div class="card-head">
      <div class="key"></div>
      <div class="chip queued">queued</div>
    </div>
    <div class="spec"></div>
    <div class="metrics">
      <div class="metric"><div class="label">elapsed</div><div class="value elapsed">00:00</div></div>
      <div class="metric"><div class="label">tokens</div><div class="value tokens">0</div></div>
      <div class="metric"><div class="label">subbies</div><div class="value childCount">0</div></div>
    </div>
    <div class="subbies"></div>
    <div class="log"></div>
    <div class="shimmer"></div>
  `;
  card.querySelector(".key").textContent = key;
  grid.appendChild(card);
  return card;
}

function updateCard(task) {
  const key = task.key || "task";
  const card = cards.get(key) || makeCard(key);
  cards.set(key, card);
  const status = task.status || "queued";
  card.className = `card ${status}`;
  const chip = card.querySelector(".chip");
  chip.className = `chip ${status}`;
  chip.textContent = status;
  card.querySelector(".spec").textContent = task.spec_short || "";
  card.querySelector(".elapsed").textContent = fmtElapsed(task.elapsed_s);
  card.querySelector(".tokens").textContent = (task.tokens || 0).toLocaleString();
  card.querySelector(".childCount").textContent = task.children || 0;
  const badge = card.querySelector(".subbies");
  if ((task.children || 0) > 0) {
    badge.textContent = `${String.fromCharCode(10551)} ${task.children} subbies`;
    badge.classList.add("on");
  } else {
    badge.textContent = "";
    badge.classList.remove("on");
  }
  const shimmer = card.querySelector(".shimmer");
  shimmer.style.opacity = status === "running" || status === "retrying" ? "1" : "0";
  const log = card.querySelector(".log");
  const lastLine = (task.log_tail || []).slice(-1)[0] || "";
  if (log.textContent !== lastLine) {
    log.textContent = lastLine;
    log.classList.remove("flash");
    void log.offsetWidth;
    log.classList.add("flash");
  }
}

function animateTokens(target) {
  target = target || 0;
  const start = displayedTokens;
  const delta = target - start;
  const startTime = performance.now();
  function step(now) {
    const t = Math.min(1, (now - startTime) / 450);
    displayedTokens = Math.round(start + delta * (1 - Math.pow(1 - t, 3)));
    document.getElementById("totalTokens").textContent = displayedTokens.toLocaleString();
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function updateElapsed() {
  if (!startedAt) return;
  const seconds = (Date.now() - startedAt.getTime()) / 1000;
  document.getElementById("elapsed").textContent = fmtElapsed(seconds);
  document.getElementById("topElapsed").textContent = fmtElapsed(seconds);
}

async function poll() {
  try {
    const response = await fetch(`/state.json?t=${Date.now()}`, { cache: "no-store" });
    const state = await response.json();
    document.getElementById("runName").textContent = state.run_name || "swarm";
    startedAt = state.started_at ? new Date(state.started_at) : startedAt;
    document.getElementById("startedAt").textContent = startedAt ? startedAt.toLocaleString() : "";
    (state.tasks || []).forEach(updateCard);
    const totals = state.totals || {};
    document.getElementById("totalRunning").textContent = totals.running || 0;
    document.getElementById("totalDone").textContent = totals.done || 0;
    document.getElementById("totalPass").textContent = totals.pass || 0;
    document.getElementById("totalFail").textContent = totals.fail || 0;
    animateTokens(totals.tokens || 0);
    updateElapsed();
  } catch (err) {
    console.error(err);
  }
}

setInterval(poll, 1000);
setInterval(updateElapsed, 250);
poll();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
