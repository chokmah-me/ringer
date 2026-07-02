# swarm.py — deterministic Codex swarm orchestrator (zero-LLM supervisor)

Build a self-contained Python 3 tool at `/Users/jonathanedwards/fleet/swarm/swarm.py` (stdlib only — no pip deps except `psycopg` which IS installed at `~/.claude/data/supabase-env/bin/python3.13`; detect and degrade gracefully to a local JSONL log at `~/fleet/swarm/runs.jsonl` if psycopg import fails).

## What it does
Reads a task manifest (JSON), fans out parallel `codex exec` workers, verifies artifacts by EXECUTING check commands, retries failures once, logs every worker-task to the fleet `swarm_runs` table, and serves a live animated dashboard.

## Manifest format (swarm.json)
```json
{
  "run_name": "my-batch",
  "workdir": "/abs/path",
  "max_parallel": 6,
  "worktrees": false,
  "repo": null,
  "tasks": [
    {"key": "t1", "spec": "prompt for codex", "check": "shell command, exit 0 = pass", "expect_files": ["a.py"]}
  ]
}
```

## Worker invocation (hard-won rules — do not deviate)
- `/opt/homebrew/bin/codex exec --skip-git-repo-check -C <taskdir> "<spec>" < /dev/null` — stdin MUST be redirected from /dev/null (codex hangs forever pre-API without it from non-TTY shells).
- Each task gets its own subdirectory `<workdir>/<key>/`. stdout+stderr tee'd to `<taskdir>/worker.log`.
- If `worktrees: true` and `repo` set: `git -C <repo> worktree add <taskdir> HEAD` before, `git worktree remove --force` after (keep on failure for debugging).
- Per-task timeout 900s (configurable per-task via `timeout_s`), kill process group on expiry.
- Parse token count from codex output if present (line like "tokens used\nN" or "tokens used: N") — best effort, null if absent.
- Retry: a task whose check fails or times out is retried ONCE with the failure output appended to the spec ("Previous attempt failed: <tail of worker.log + check output>. Fix it.").

## Verify
After worker exits: (1) all `expect_files` exist and are non-empty; (2) run `check` in the taskdir with 60s timeout; exit 0 = PASS. Record the check's stdout+stderr RAW (first 2000 chars) — never summarize.

## Eval logging
One row per attempt into Supabase `swarm_runs` (creds: parse `~/.claude/data/supabase.env` for SUPABASE_DB_HOST/PORT/USER/PASSWORD/NAME — strip quotes). Columns: run_id (run_name + timestamp), pattern='swarm-py', task_key, spec (first 500 chars), worker_engine='codex gpt-5.5', shepherd_model='none (swarm.py)', verify_method='executed-check', verdict PASS/FAIL/TIMEOUT/ERROR, duration_ms, worker_tokens, notes (raw check output excerpt + retry flag).

## Live dashboard — make it look BADASS
- swarm.py continuously writes `~/.swarm/state.json`: {run_name, started_at, tasks: [{key, status: queued|running|verifying|retrying|pass|fail, spec_short, elapsed_s, tokens, children: <count of live codex child processes detected under the worker pid>, log_tail: last 3 lines of worker.log}], totals: {running, done, pass, fail, tokens}}.
- `--dashboard` (default ON) starts a stdlib http.server on port 8787 (fall back +1 if busy) serving a single-page dashboard at / and state at /state.json; auto-opens browser via `open http://localhost:PORT`.
- Dashboard page: dark theme, single self-contained HTML string in the python file. JS polls /state.json every 1s. Design: title bar with run name + animated pulse dot; grid of task cards, each card shows key, status chip (color: queued gray, running animated cyan glow/pulse, verifying amber, pass green, fail red), elapsed ticking clock, token count, a subtle animated progress shimmer while running, "⤷ N subbies" badge when children > 0, and the last log line in monospace fading in on change. Footer: totals row + aggregate token burn counting up + elapsed. Smooth CSS transitions, no external assets, no frameworks. It should feel like a mission-control spinner — alive, glanceable, cool.
- Nested-worker detection: walk `ps -eo pid,ppid` to count codex processes descending from each worker pid → that's the "subbies" count.

## CLI
`swarm.py run manifest.json [--max-parallel N] [--no-dashboard] [--dry-run]`
`swarm.py demo` — generates a 3-task toy manifest in /tmp and runs it (use trivial file-writing tasks).
`--dry-run` prints the plan without spawning codex.

## Quality bar
Clean, readable, well-factored (Manifest, Worker, Verifier, EvalLogger, StateWriter, Dashboard classes or clear function groups). Graceful Ctrl-C: kill all workers, final state flush, summary table to stdout. No global mutable soup. Type hints. A `--help` that a stranger could use.

Write the complete file, then run `python3 -m py_compile swarm.py` to prove it parses, then run `swarm.py run --dry-run` against a generated demo manifest to prove the plumbing works WITHOUT spawning codex (do NOT run actual codex workers — the reviewer will do the live test). Reply DONE + a one-paragraph summary of design decisions.
