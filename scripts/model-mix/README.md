# Model-mix refresh (twice weekly)

Scheduled job that infers **what you are working on** and produces a **Ringer engine/model mix brief**.

## What it does

1. **Collect** evidence: `session-recall-cc`, `Documents\00Dev` git, `~/.ringer/runs.jsonl`, home memory (`model-pool-current.md`), `ringer.py models`.
2. **LLM brief** (Grok headless first, Claude `-p` fallback): ringer-brief-style **routing only** — no swarm runs.
3. **Publish** to `~/.ringer/model-mix/latest.md` and `latest.json`.

## Paths

| Item | Path |
|------|------|
| Collect | `Collect-WorkSignals.ps1` |
| Invoke | `Invoke-ModelMixBrief.ps1` |
| Install schtasks | `Install-ModelMixTask.ps1` |
| Prompt | `prompts/model-mix-brief.md` |
| Outputs | `%USERPROFILE%\.ringer\model-mix\` |

## Manual run

```powershell
# Evidence only
& "$env:USERPROFILE\Documents\00Dev\ringer\scripts\model-mix\Invoke-ModelMixBrief.ps1" -SkipLlm

# Full brief (Grok first, then Claude; or force one provider)
& "$env:USERPROFILE\Documents\00Dev\ringer\scripts\model-mix\Invoke-ModelMixBrief.ps1"
& "...\Invoke-ModelMixBrief.ps1" -Provider grok

Get-Content "$env:USERPROFILE\.ringer\model-mix\latest.md"
```

## Install / uninstall schedule

Default: **Tuesday and Friday 09:00**, current user, **only when logged on** (`/IT`) so Claude OAuth works.

```powershell
& "$env:USERPROFILE\Documents\00Dev\ringer\scripts\model-mix\Install-ModelMixTask.ps1"
& "$env:USERPROFILE\Documents\00Dev\ringer\scripts\model-mix\Install-ModelMixTask.ps1" -Time 08:30

# Force run once via Task Scheduler
schtasks /Run /TN "Ringer\ModelMixRefresh-Tue"

# Remove
& "...\Install-ModelMixTask.ps1" -Uninstall
```

## Using the result

When authoring a Ringer manifest (or `/ringer-brief`), open `latest.json` and set per-task `engine` / `model` from `projects.<name>.by_task_type`.

This job **does not** auto-run swarms or edit `config.toml`.

## Standing locks

| task_type | locked routing | where enforced |
|-----------|----------------|----------------|
| **probe** | `opencode` / `deepseek/deepseek-v4-pro` | `prompts/model-mix-brief.md` (constraint 7), heuristic fallback in `Invoke-ModelMixBrief.ps1` |

Do not change probe defaults in generated briefs without updating that prompt lock.
