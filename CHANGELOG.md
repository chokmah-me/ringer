# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)-style sections under dated headings.

## 2026-07-16

### Fixed

- **`templates/repo-feature` check no longer false-fails on pytest tool noise.**  
  `checks/check_repo_feature.py` always allowlists `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `.nox/`, `*.pyc` / `*.pyo` / `*.pyd`, and similar runner caches at any path depth.  
  Previously, a green `pytest` that left `?? src/__pycache__/` marked the task FAIL, which triggered Ringer’s automatic retry and wasted frontier tokens (2026-07-16 Kimi K3 vs Opus/Fable bakeoff).

### Added

- **`templates/repo-feature/seed.gitignore`** — copy into audition/fixture seeds and commit before the run so bytecode never appears in porcelain status under older check copies either.
- **`tests/test_check_repo_feature.py`** — offline unit + integration coverage for noise allowlist, ownership fails, and `--allowed-status` extras.
- **Orchestrator rule** (`.claude/skills/ringer/SKILL.md`): never re-run a frontier model matrix when build/tests already passed and the only FAIL is git-status allowlist noise — fix the check and re-check only ($0).
- **MODEL-NOTES:** first outing for `openrouter/moonshotai/kimi-k3` (probation for cost-sensitive `code-feature`; slower than Opus/Fable on the medium priority-queue fixture).

### Changed

- `templates/repo-feature/README.md`, `manifest.json` `verified` text, and `templates/bakeoff/README.md` document built-in noise defaults and the no-rerun-on-harness-noise gotcha.
- Check FAIL banner distinguishes **build/test failure** from **git-status ownership after green tests**, with a re-check-only hint.

### Notes

- Worker-invented `.gitignore` is still an ownership violation unless that path is owned — seed it in the fixture instead of letting models create it.
- Ringer’s single automatic retry is unchanged; noise simply no longer produces a FAIL that would consume it.
