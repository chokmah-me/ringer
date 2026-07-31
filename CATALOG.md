# ringer system catalog

## ringer — verified AI-agent swarm delegation

- **owner:** chokmah-me (local fork operator); upstream author Nate B Jones (github.com/NateBJones-Projects/ringer)
- **status:** active
- **purpose:** Run parallel AI-agent swarms that prove their work: a premium model writes specs and reviews; cheap worker CLIs do the implementation in parallel; every result is verified by **executing a check command** against the artifact, not by trusting the worker's "done." Ships Ringside, a live browser dashboard of all local swarms.
- **inputs:** `manifest.json` (task specs + check commands); a worker engine CLI (`codex exec` default; `engines/mock_worker.py`, `engines/opencode-sandboxed.sh`); optional `~/.config/ringer/config.toml`.
- **outputs:** `~/.ringer/runs/` artifacts; eval log (JSONL or Postgres); Ringside web page (auto-opened); verified deliverables harvested per the manifest.
- **dependencies:** Python 3.11+ (`tomllib`); a worker CLI (Codex / Grok / opencode) installed and authed; stdlib + `sqlite3`; optional Postgres. Confirmed running natively on Windows (see 2026-07-30 note below) as well as macOS/Linux.
- **credentials/permissions:** worker-CLI auth (e.g. `codex login` on a ChatGPT plan) and the model access it carries; Ringer itself holds no secrets.
- **failure modes:** Parallel workers report false "done" — mitigated by executed checks + one retry with failure context injected. Missing/unauthed worker CLI → runs fail immediately.
- **test_evidence:** `python -m pytest -q` on Windows, 2026-07-19 → **142 passed, 16 failed, 1 skipped**. The 16 failures are Windows-environment-specific (temp-path / file-op / design-reference cases). Separately, 2026-07-30: 5 real end-to-end manifest runs (`run`, `lint`, `--dry-run`, `models`, `catalog --refresh`) executed natively on Windows 11 against `ringer-bakeoff-kit`, 25 total task attempts across the `opencode` engine, no WSL — see decision note below.
- **last_validated:** 2026-07-30
- **confidence:** fresh

README.md + `docs/` hold the full guide; the repo `CLAUDE.md` carries the routing rule.
The `ringer` and `ringer-brief` skills in `~/.claude/skills/` are the orchestrator
playbook and the manifest-authoring helper.

Decision note (2026-07-19): the Windows pytest run is a **smoke check** of core logic
only — the 16 failures are platform artifacts, not regressions. Treat green CI on a
supported OS as the real gate; `last_validated` here means "core suite confirmed runnable,"
not "fully green on this box." Local remote is the `chokmah-me/ringer` fork; upstream is
`NateBJones-Projects/ringer`.

Correction (2026-07-30): the prior "Windows via WSL only" / "no native Windows support"
claims above were wrong, not just stale — `run`, `lint`, `--dry-run`, `models`, and
`catalog --refresh` all worked natively on Windows 11 across a 5-round, 25-attempt
bakeoff (`~/Documents/ringer-bakeoff-kit`, DECISIONS.md there has the full record).
The `[engines.opencode]` block in `config.sample.toml` already documents the Windows
path (`opencode.cmd`, no sandbox layer); checks route through Git Bash
(`ringer.py`'s `_run_check`, since `cmd.exe` chokes on bash constructs like
`{ ...; exit 1; }`). Codex engine's Windows note (`codex.cmd` shim) was not
independently re-verified this pass — only opencode was exercised. If a future pass
re-confirms Codex on Windows too, promote this from engine-specific to
unconditionally "runs on Windows."
