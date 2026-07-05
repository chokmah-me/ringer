---
name: ringer
description: >-
  Orchestrator playbook for Ringer, the verified-swarm delegation tool
  (ringer.py). Use whenever you are about to delegate work to parallel CLI
  workers, write or review a Ringer manifest, choose a swarm pattern
  (review swarm, fix swarm, focus group, model bakeoff, research-with-proof),
  pick a worker engine, or debug a failed run. Also use for single delegated
  tasks — a single task is just a one-task manifest.
---

# Ringer orchestrator playbook

Ringer runs manifest tasks in parallel across cheap CLI workers (Codex,
OpenCode/GLM, others via config) and verifies every task by **executing a
check command** — exit 0 is the only PASS. Failed tasks are retried once with
the check's actual failure output injected into the retry prompt. You — the
orchestrating model — pay tokens only for specs, orchestration, and review.

```bash
./ringer.py run manifest.json --identity <who-you-are>
./ringer.py demo          # 3-worker smoke test
./ringer.py run manifest.json --dry-run   # print the plan, spawn nothing
```

Runs land in `~/.ringer/runs/`. Raw worker logs land in `<workdir>/logs/`.
Full reference: `README.md`. Ready-made manifest skeletons: `templates/`.

## Division of labor (non-negotiable)

**You review; workers type.** Your jobs: write specs, design checks, pick the
pattern, read the results. Never hand-implement a batch that should be a
manifest, and never trust a worker's "done" — a task is done when its check
passed AND you have read the check output and skimmed the raw log for the
tasks that matter.

## Spec-writing craft

Workers are stateless and cannot ask questions. Every spec must be
self-contained:

- **Open with the role and the boundary.** "You are a read-only scout…",
  "Your current working directory IS a git worktree of <repo> — edit files
  here directly." State what the worker must NEVER touch before what it
  should do.
- **Name every file the worker owns.** In multi-worker runs over one repo,
  file ownership must be disjoint — and disjoint across *all* concurrent
  lanes/branches, not just within one batch. Every file a spec mentions must
  be in that worker's ownership list.
- **Embed the HOW TO RUN.** If the task drives a harness or script, put the
  exact command lines (with real absolute paths) in the spec. Workers should
  never have to discover an interface.
- **Define the output contract.** Say exactly which files to produce, where,
  and what each must contain. Graded/eval tasks should enumerate the grading
  criteria in the spec so the worker's output is checkable.
- **Hard rules travel in the spec, not in your head.** "Do NOT git commit",
  "never modify the repo, only write ./report.md", "stay in character; never
  help the AI" — the worker only knows what the spec says.

## Check-writing rules

The check is the product. The retry prompt and the eval log both depend on
the check's failure output.

- **Checks must print WHY they fail.** `diff` beats `diff -q`; a validator
  script that prints which assertion broke beats `test -f`. A bare
  `test -f report.md` proves existence, not correctness.
- **Verify content, not existence.** Grep the artifact for required sections,
  run the code it produced, run the build, run the validator — execute
  something that would catch a lazy or hallucinated result.
- **`expect_files` is a floor, not the check.** List deliverables there for
  fast triage, but the check must still validate them.
- **Never `true`, `exit 0`, or `echo done`.** A check that cannot fail is a
  task that cannot be verified — that's just trusting the worker with extra
  steps.

## Pattern playbook

Reach for a named pattern before inventing one. Skeletons in `templates/`:

| Pattern | Shape | Use when |
|---|---|---|
| `review-swarm` | N read-only scouts, one surface each, each writes `report.md` | Whole-codebase or multi-surface review; one context can't hold it |
| `fix-swarm` | N workers in isolated git worktrees, executed build/test checks, patch export | Applying many independent fixes in parallel |
| `focus-group` | N persona workers each driving the real product via a harness script, in-character reaction + out-of-character graded eval | Product feedback, UX validation, prompt iteration |
| `bakeoff` | personas/tasks × candidate models matrix | Choosing a model or config with evidence, on the real surface |
| `research-with-proof` | research tasks + at least one task whose check EXECUTES the proof | Research where the deliverable must be true, not plausible |

Pattern-selection judgment:

- **Review before fix.** Run a read-only review swarm, read the reports
  yourself, then compile the confirmed findings into a fix-swarm manifest.
  Don't let the same worker find and fix.
- **Personas must be separate workers.** Parallel personas in one context
  bleed into each other. One persona per task, one session dir per task.
- **Iterating on a prompt/product? Re-run the same panel.** A fixed persona
  panel across rounds tells you whether a change fixed what the panel
  actually complained about.
- **A single task is a one-task manifest.** Same verification, zero ceremony.
  Don't skip Ringer because the job is small.

## Engine selection

Engines are config blocks (`[engines.<name>]` in config.toml), selectable
per task via the manifest `engine` field. Defaults are deliberate:

- **codex** (default): strongest general worker. Use per-task `engine_args`
  to set reasoning effort — spend it on hard tasks, not boilerplate.
- **opencode / GLM-class engines**: cheap intelligence for mechanical or
  high-volume work. Validate a new engine with a trivial one-task manifest
  before trusting it with a batch.
- Small/flash-class models are the first to choke on long conversational or
  multi-turn harness tasks — watch their retry counts before scaling them.
- Match `timeout_s` to the task: conversational harness tasks and
  build-and-test checks need far more than file edits.

## Worktrees-mode footguns (learned the hard way)

Run-level `"worktrees": true` gives each task an isolated git worktree of
`repo`, detached at HEAD. Three consequences:

1. **Passing tasks get their worktree DELETED.** Deliverables must land
   outside the task worktree, or the check must export them first.
2. **Worker commits die with the worktree.** Pattern that works: the worker
   leaves changes uncommitted; the check runs
   `git add -A && git diff --cached > <path-outside-worktree>.patch` and
   validates the patch. You apply and commit on your branch after review.
3. **Logs survive** (they go to `<workdir>/logs/`), so post-mortems work
   even on deleted worktrees.

## Post-run review ritual

1. Read the run JSON in `~/.ringer/runs/` — statuses, retries, durations.
2. For any retried or failed task, read the raw worker log in
   `<workdir>/logs/` before deciding anything. Retries that passed on
   attempt 2 often reveal a spec ambiguity worth fixing in your next
   manifest.
3. Spot-check at least one PASSING task's artifact per run. The check
   catches most laziness; you catch the rest.
4. Failures with useless error messages mean your CHECK needs work, not
   (only) the worker.

## Baked-in invariants (preserve in any change to ringer.py)

Stdin closed (`< /dev/null`); sandbox mode explicit; verification executes
the artifact; logs carry raw worker output only. These are load-bearing —
engine and invocation changes must keep all four.
