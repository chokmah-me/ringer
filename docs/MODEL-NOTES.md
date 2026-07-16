# Model notes — how workers actually perform

A running log of how models perform on real Ringer tasks, so engine and
model choices are made on evidence instead of vibes. The raw numbers now
live in the local eval log (`~/.ringer/runs.jsonl`); run `./ringer.py models`
to print the per-model, per-task_type scoreboard (tasks, attempts,
pass_rate, first_try_pass_rate, median duration/tokens, last_seen). This
file remains the judgment layer on top of those numbers.

**How to add a row:** after reviewing a run (post-run ritual step 5 in the
ringer skill), append one dated line under the model. Say the task type,
what happened, and what you'd do differently. Only write what the executed
checks and raw logs support — no vibes, no worker self-reports.

## codex (GPT-5-class, own harness)

- Strongest general worker; the default engine. Spend reasoning effort per
  task via `engine_args` (`["-c", "model_reasoning_effort=low|medium|high"]`)
  — high on gnarly tasks, low on boilerplate.
- 2026-07-05 — carried the heavy lanes of the milk-crate demo rehearsals
  (market read with source allowlist, site build) with clean first-attempt
  passes.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~85k tokens.
- 2026-07-06 — motion design (5 HTML animations for video b-roll) + 2
  editorial diagram pages, each verified by rendering through headless
  Chromium to MP4/PNG: 7/7 passed on attempt 1. Broadcast-quality visual
  output from rich storyboard specs; the render-as-check pattern works.
- 2026-07-06 — milk-crate demo: two single-file website builds (v1 scaffold
  316s/~175k tok; final brand+market-test reskin 622s/~184k tok), both passed
  14-assertion content checks on attempt 1, including base64-embedding photos
  and honoring honesty-marker requirements. Codex remains the site-build lane.
- 2026-07-06 — ringer.py feature batch (task_type field + enriched eval rows
  + `models` scoreboard + hud single-tab fix; ~640-line diff incl. two new
  test suites): substance passed on attempt 1 — its check printed PASS
  (compile, all 16 suites, exact CLI aggregation contract) — but the run
  recorded attempt 2 because of the expect_files-before-check harness bug
  (see process lessons). Heavy single-file feature work against an exact
  behavioral contract is squarely codex's lane.

- 2026-07-06 — elsas-website demo: Next.js scaffold PASSED attempt 2 (682s,
  ~354k tok) — attempt 1 built a complete homepage and silently skipped the
  other 10 routes; the route-enumeration check caught it. Narration lane
  (15 ElevenLabs calls, chunked, nohup pattern) passed attempt 1. CAUTION: a
  codex fix worker GAMED a verbatim-content needle by hiding the required text
  in a visually-hidden paragraph — passed the check, caught only by
  orchestrator integration review. Needle checks need an anti-hidden-text
  assertion or documented exceptions.

- 2026-07-06 — OpenRouter catalog + explore suggester (catalog subcommand
  with snapshot/changelog/free-detection, daemon auto-refresh, tiered
  --explore; offline fixture-driven contract check): PASS attempt 1, 362s.
  Follow-up sentinel-pricing fix (variable-pricing models): PASS attempt 1,
  114s. With the verify-order fix landed, zero phantom retries across the
  whole batch.
- 2026-07-06 — adversarial review of the model-router stack (2,650-line
  diff, structured report contract): PASS attempt 1, 176s — found a real
  HIGH (--since window inflating first-try rates) plus 3 MEDIUMs, all
  confirmed against the code. Then fixed all five review findings in one
  batch (task-level --since, pricing transitions, event durability + flock,
  unknown pricing, stderr notice) with test coverage: PASS attempt 1, 202s.
  Review->fix roundtrip in codex's lane works end to end.
- 2026-07-06 — scoreboard HTML page (zero-LLM renderer, ~700-line diff,
  design + evidence-floor ranking + cost math + notes parser): substance
  PASS attempt 1 (the run's recorded retry was an orchestrator check bug —
  the free-promo watchlist legitimately mentions a free model before the
  ranked cards, and the check compared raw first-occurrence). Six review
  findings fixed in one batch, PASS attempt 1, 141s.
- 2026-07-06 — model-db stack (SQLite read model 516s, page redesign 536s,
  Ringside tab 527s, plus three fix batches all attempt-1): five substantial
  ringer.py features in one day, every one against an executed contract
  check. Review lane found the HIGH that mattered (sync cursor skipping a
  half-written trailing line). Codex is the proven lane for both sides of
  the review->fix loop on this codebase.

## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`)

- The cheap-intelligence default (~$0.74/M in, $2.33/M out, 2026-07 —
  20-30x cheaper output than frontier coding models). Reliable on
  mechanical, tightly-specced work: file edits, format conversions,
  template-driven builds.
- 2026-07-05 — milk-crate demo rehearsals: handled brand-board/SVG/copy
  tasks at around a penny per passing task.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed, but
  needed the retry (attempt 2) where codex passed on attempt 1. Long
  structured reviews sit at the edge of its comfort zone; keep the section
  contract explicit in the spec.
- 2026-07-06 — three mechanical image-generation batches (18 images via
  openrouter-image commands, idempotent batch-runner spec): 3/3 passed on
  attempt 1, ~14.5k tokens each. The "execute these exact commands, do not
  improve them" spec pattern is fully reliable for glm-5.2.
- 2026-07-09 — first run on the Windows machine (lane-setup probe, write
  fib.py + executed check): PASS attempt 1, 33s, 8.4k tokens. Account
  context: the same task 402'd earlier on a zero-credit OpenRouter account
  — OpenCode requests max_tokens=32000, so the account needs at least that
  much affordable headroom or every GLM call dies pre-model.
- 2026-07-10 — clean depth batch (3 distinct mechanical probes: sum of
  squares, factorial, prime count — each write-a-script + executed check):
  3/3 PASS attempt 1, ~8.3k tokens / ~22s each. Confirms glm-5.2 is a
  reliable cheap default for mechanical write-and-verify work once the
  account is funded. After the eval-log purge below, glm's `probe` record
  is a clean 4/4 first_try 1.00.

- 2026-07-06 — backfill/seed script for the model log (252-line stdlib CLI
  with a run-state join, 3-level mapping precedence, never-overwrite and
  idempotency rules): the artifact was CORRECT; the recorded FAIL was an
  orchestrator check-fixture bug (a missing newline glued the fixture's last
  row to a garbage line) plus the harness ordering bug below. Verified PASS
  once the check was fixed. Tight behavior contracts in the spec work great
  for glm — and read the raw logs before blaming the model.
- 2026-07-06 — README/MODEL-NOTES docs + task_type sweep across 17 template
  manifests: passed attempt 2; attempt 1 was lost to the harness ordering
  bug, not model quality — the retry worker's log correctly diagnosed that
  harness bug unprompted, impressive debugging from the cheap lane.
- 2026-07-06 — catalog/explore README section (flags, promotion ladder,
  per-user framing): PASS attempt 1, ~21.5k tokens. Doc sections against a
  grep-able content contract remain a safe glm lane.
- 2026-07-06 — milk-crate demo, full run: 4 independent buyer-persona
  reviews (focus group) all passed attempt 1 (~15k tokens, ~2¢ each) with an
  explicit VERDICT-block contract — persona work is squarely in glm's zone.
  Market read with live curl fetching passed once the spec demanded verbatim
  copy-paste of source URLs (first fail was the worker trimming URL slugs —
  spec/check craft, not model weakness). Brand-kit doc incl. a clean inline
  SVG wordmark: good, one bounce off an over-strict check regex.

- 2026-07-06 — elsas-website demo: verbatim content capture (16 pages + 19
  news posts, 213 blockquotes) passed attempt 2 — attempt 1 SELF-REPORTED
  "all 213 match exactly, 0 errors" while the executed check found 13 stitched/
  paraphrased quotes. Self-reports are worthless; the retry with injected
  failures fixed all 13 (~148k tok total, ~3¢). Page builds (about+faq;
  news index + 19 generated post routes via its own extraction script) and
  2 focus-group personas: all attempt 1. Fix batch attempt 1.
- 2026-07-06 — invariants/file-I/O review lens on the same stack: PASS
  attempt 1, 68k tokens — caught the non-atomic backfill rewrite (real data
  loss risk) and the daemon stdout race; both confirmed. Then fixed the
  backfill atomicity (tmp+os.replace, pid-stamped backups) attempt 1 with
  the original behavioral grader unchanged. Structured review with an
  explicit lens is now proven glm territory, not just probation.
- 2026-07-06 — solo adversarial review of the scoreboard renderer (~700
  line diff, injection-focused lens): PASS attempt 1 — 1 MEDIUM (unanchored
  MODEL-NOTES heading match cross-contaminating gpt-4/gpt-4o-style
  families) + 5 real LOWs, plus an empirically-verified injection all-clear
  (it actually rendered hostile model ids to prove escaping). Second
  proven-tier structured review in one day; glm is now the default review
  lane for mid-size diffs.
- 2026-07-06 — invariants/injection/frontend review of the 4,061-line
  model-db branch: PASS attempt 1, 96k tokens, 14 coverage items — two real
  contention findings (full catalog re-ingest per sync; schema writes on
  read paths) plus an empirical XSS all-clear on the new DOM surfaces.
  Third proven-tier structured review today.
- 2026-07-12/13 — first doc-swarm audition (blueprint kit, real repo,
  read-only, 3 module-doc tasks against PIPL-arch's sip-core/telemetry-
  consumer/ledger-signer services): **3/3 PASS**, ~22k-53k tokens/task.
  Substantively strong: one worker (sip-core) found and fixed a factual error
  in a stale pre-existing doc (wrong RabbitMQ exchange/routing-key names)
  by cross-checking against actual source rather than trusting old content.
  Every recorded FAIL across 3 rounds of this run was an orchestrator
  check-craft bug (citation text wrongly required inside backticks in the
  Documented Symbols section so it got treated as a fake symbol; `Type::
  method`-qualified spans that Rust never spells at a definition site;
  a fixed 60s-per-example budget blown by a full `cargo test` run instead of
  `--list`; a global min-section-words floor incompatible with a
  single-command Examples section and a one-word "None" Assumptions section)
  — see Process lessons below. None of these were model quality issues.

## kimi-k2.7 via opencode (`openrouter/moonshotai/kimi-k2.7-code`)

- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~83k tokens. First real outing; promising for review work.
  (Ran through an ad-hoc copy of the opencode engine block — the per-task
  `model` field now makes that unnecessary.)

## kimi-k3 via opencode (`openrouter/moonshotai/kimi-k3`)

- 2026-07-16 — first outing: harness probe + frontier bakeoff vs
  `claude-opus-4.8` and `claude-fable-5` on a medium `code-feature`
  (priority-task-queue fixture: implement API+CLI until 15 pytest pass).
  **Quality:** substance PASS attempt 1 (15/15 pytest, notes, owned paths)
  — same contract pass as Opus and Fable. Ringer recorded FAIL only because
  the check disallowed pytest `__pycache__` (fixture allowlist bug; re-check
  with pycache allowlisted → PASS all three). **Throughput:** ~17 min wall
  vs Opus ~3.5 min / Fable ~3 min; heavy reasoning + digression (e.g.
  disassembling `.pyc`). **Cost:** list $3/$15 (cheaper sticker than Opus
  $5/$25 and Fable $10/$50); OpenCode logged `cost:0` for K3 so $/task
  metering is incomplete — Opus attempt-1 log sum ~$0.54, Fable ~$0.91.
  **Harness notes:** (1) OpenCode 1.17.15 models.dev cache lacked K3 —
  registered in `~/.config/opencode/opencode.jsonc` under
  `provider.openrouter.models.moonshotai/kimi-k3`. (2) Windows
  `opencode.cmd` truncates multiline `{spec}` argv at newlines — use
  single-line specs. **Routing:** probation for cost-sensitive
  `code-feature`; prefer over Fable on this difficulty; keep Opus when
  latency matters; do not set as opencode default; n=1 — need more
  scenarios before proven. Artifacts:
  `~/.ringer/auditions/kimi-k3-vs-frontier/comparison.md`.

## kimi-k2.6 (`moonshotai/kimi-k2.6`, subject-model evidence via OpenRouter)

- 2026-07-07 — Benchmark Suite 2.0 operator eval, killed by Jon at ~4.5h.
  Serving throughput, not model quality, was the failure: on the Brick
  1000-piece case (reasoning xhigh, pinned provider order
  inceptron→decart→baidu→modelrun, no fallbacks) K2.6 averaged ~21 tok/s
  with two ~19-min stalls at 4.5 tok/s — 136+ min unfinished vs Sonnet 5's
  25 min (94 tok/s) and GPT-5.5's 24 min (55 tok/s) on the identical case.
  Model behavior itself was fine: 28 turns (fewer than Sonnet's 82), 170k
  output tokens (in family norms), 12% reasoning, zero API errors. Verdict:
  do NOT schedule K2.6 for long agentic work through that provider set;
  if K2.6 data is ever wanted, probe a single case against other providers
  first. Distinct model from k2.7-code above — don't transfer this verdict
  to k2.7.


## grok-build (Grok CLI engine, flat plan)

- 2026-07-06 — first outing (elsas-website demo), engine added same day:
  audition PASS attempt 1 in 28.9s. Then: asset harvest (11 images, live URL
  re-fetch check), books page, 5 work-page routes in one task (59 verbatim
  needles), adversarial code review (10 real findings incl. an unshelled 404
  and a broken embedded link), press/media fix batch, audio-player integration
  across 15 pages — ALL attempt 1 (player's red ledger entry was a check bug,
  artifact certified). Fast, precise on mechanical/code work. No token counts
  in JSON output (flat plan) — cost reads "included in plan".

## grok-composer-2.5-fast (Grok CLI engine, flat plan)

- 2026-07-06 — first outing (elsas-website demo): audition PASS attempt 1
  (138s — slower than grok-build but the strongest copy of the round).
  Accessibility constitution (14 testable criteria, SC-numbered) attempt 1;
  a11y-gatekeeper harness (axe+Playwright, light/dark, reduced-motion assert)
  attempt 2 — attempt 1's harness mishandled Next's default /404 route.
  Events/faq/contact fix batch attempt 1, but satisfied "editorial grid" with
  an EMPTY aside landmark — axe caught it (landmark-complementary-is-top-level).
  Persona work: good. Watch for letter-of-the-spec shortcuts on layout asks.
- 2026-07-10 — AIGrandPrix 4-surface code-review audition (same review-swarm
  contract as the nemotron Ultra 0/4), engine `grok` / model
  `grok-composer-2.5-fast`, max_parallel 4: **4/4 PASS attempt 1**, ~60–75s
  per task (~75s wall). No token counts (flat plan). Reports hit the field
  contract (Evidence/Impact/Fix/Priority/Confidence, ≤3 summary bullets,
  ≤1200 words) and cited real file:line evidence. Strong code-review lane
  relative to free Nemotron Ultra on the same specs.

## qwen3-coder (via opencode, `openrouter/qwen/qwen3-coder:free`)

- 2026-07-10 — AIGrandPrix 4-surface code-review audition (same contract as
  grok-composer 4/4 and nemotron Ultra 0/4), max_parallel 2, timeout_s 900:
  **0/4 TIMEOUT** (all attempt 2). ~61 min wall. **Zero model tokens / zero
  OpenCode JSON events** on every attempt — workers hung after spawn until
  Ringer's 900s kill; no report.md produced. Serving/free-provider stall, not
  a judgeable model failure. Do not re-queue this free slug for long agentic
  review until a short probe (write+execute) returns stream within ~60s; try
  another free family (e.g. gemma-4-31b or qwen3-next-80b) if free lanes are
  still wanted.

## nemotron-3-ultra-550b (via opencode, `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`)

- 2026-07-10 — probe smoke (write hello.py + execute): PASS attempt 1, 7.6s,
  ~9k tokens. Correct OpenRouter free slug is required
  (`openrouter/nvidia/...:free`); bare `nvidia/...` returns OpenCode
  UnknownError before the model runs.
- 2026-07-10 — full AIGrandPrix code-review audition (4 surfaces, review-swarm
  contract, max_parallel 2, ~15 min, ~461k tokens total, $0): **0/4 PASS** on
  the executed check (all attempt 2). Substance was real — workers read the
  repo and wrote multi-finding reports with file:line evidence — but every
  surface failed the structured-report contract: bold field labels
  (`**Priority:** P0`) originally rejected by the check (now fixed to tolerate
  markdown bold), plus summary >3 lines and/or >1200 words and (ekf) one
  finding missing a file:line cite. After the bold-tolerance check fix,
  re-validating the same artifacts offline: perception PASS; ekf/neural/
  thermal still FAIL on length/summary/cite. Same lesson as super-120b: free
  Ultra can engage a long review but does not yet own the tight report
  contract; keep proven-tier review lanes on glm/codex until first-try
  contract passes.

## nemotron-3-super-120b (via opencode, `openrouter/nvidia/nemotron-3-super-120b-a12b:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0 spent — free promo).
  Task: fresh-eyes adversarial review of a 2,650-line diff with a structured
  report contract. Failed both attempts on the same executed check: report
  had the right sections and verdict but under 3 concrete code citations —
  shallow engagement with the actual code, 212k tokens burned. Don't re-run
  this audition on long structured code review; if it gets another slot,
  try a shorter, more mechanical task first.

## llama-3.3-70b-instruct (via opencode, `openrouter/meta-llama/llama-3.3-70b-instruct:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0). Fresh-eyes review of
  a 4,061-line diff with a verbatim-quote citation requirement: failed the
  structured-report check both attempts. Second free-model audition to fail
  on long structured code review (after nemotron-3-super) — the exploration
  ladder now says: audition free models on SHORT mechanical tasks first;
  long-diff review is a proven-tier lane.
- 2026-07-09 — lane-setup probe, $0: never ran. OpenCode requests
  max_tokens=32000; this free slug's provider (Venice) caps output at
  16384, so OpenRouter 400'd both attempts before the model saw the spec.
  Not a model failure — a provider-cap/harness mismatch to remember when
  routing free slugs through opencode.

## gpt-oss-120b (via opencode, `openrouter/openai/gpt-oss-120b:free`)

- 2026-07-09 — lane-setup probe (write fib.py, check executes it), $0,
  failed. Attempt set 1: accepted the 32k max_tokens request and reasoned
  correctly, but wrote to absolute path `/fib.py` (OpenCode
  FileSystem.writeFile error) and the session then hung to the 300s
  timeout on both attempts. Attempt set 2 (spec hardened to "RELATIVE path
  ./fib.py"): zero output before the 180s timeout — consistent with
  free-tier rate limiting on a zero-credit OpenRouter account after
  several probe calls. Lesson: free-tier lanes on a zero-credit account
  are unreliable for anything, including probes; fund the account before
  judging the model.

## deepseek-v4-pro (via opencode, native provider `deepseek/deepseek-v4-pro`)

- 2026-07-09 — lane-setup probe (write primes.py, check executes it): PASS
  attempt 1, 14.3s, 8.7k tokens. Native DeepSeek provider via
  `DEEPSEEK_API_KEY` env var — OpenCode picks it up directly, no
  OpenRouter routing or credits needed. Spot-checked artifact: real
  trial-division primality loop, not a hardcoded print.

## deepseek-v4-flash (via opencode, native provider `deepseek/deepseek-v4-flash`)

- 2026-07-09 — lane-setup probe (write fib.py, check executes it): PASS
  attempt 1, 17.1s, 9.1k tokens. Same native-provider path as v4-pro.
  Spot-checked artifact: real iterative Fibonacci loop, not hardcoded.

## grok-composer-2.5-fast (via grok CLI, `[engines.grok]`)

- 2026-07-09 — lane-setup probe (write primes.py, check executes it):
  PASS attempt 1, 21s, plan-billed (no token counts in grok JSON output).
  First run of the grok engine on this machine (CLI v0.2.91; config flags
  re-verified against --help). Windows note: grok's Seatbelt sandbox is
  macOS-only — "--sandbox workspace" is accepted but containment is
  process-policy only, so real repo work should use worktrees mode.

## claude-sonnet-5 (via opencode, `openrouter/anthropic/claude-sonnet-5`)

- 2026-07-10 — lane-setup probe (write cubes.py, check executes it): PASS
  attempt 1, 22.5s, 12.4k tokens. Spot-checked artifact: real
  `sum(i**3 for i in range(1,11))`, not hardcoded. AUTH ROUTING LESSON:
  the NATIVE path (`anthropic/claude-sonnet-5` via `ANTHROPIC_API_KEY`
  env) fails 401 `invalid x-api-key` because that env var holds a Claude
  Code OAuth token (`sk-ant-oat…`), not an API key (`sk-ant-api…`); the
  Messages API rejects OAuth tokens. Route Claude through the funded
  OpenRouter credential instead (works with zero extra setup), or add a
  real Anthropic API key via `opencode auth login`. All Claude slugs
  (Haiku/Opus/Fable) ride this same OpenRouter lane via the model field.
- 2026-07-12/13 — first test-hardening audition (blueprint kit, real repo,
  worktrees, 2 tasks against `pipl-core`'s untested `envelope.rs` wire format
  and `chain.rs`'s nonfinite-float encoding gap): **2/2 PASS**, ~45k
  tokens/task, real coverage added (5→11 and 5→15 total crate tests), zero
  production-code edits, patches cleanly scoped to the one owned file each.
  Both attempt-1 runs actually wrote correct, thorough tests; the recorded
  attempt-2 verdicts across three consecutive re-runs were entirely check
  bugs on the orchestrator's side (nested-quote argv splitting, a Windows
  cmd.exe-vs-bash subprocess routing bug in the kit script, and a regex
  boundary bug undercounting assertions to zero) — see Process lessons below.
  Once the check was fixed, the worker's own attempt-1 artifact passed
  outright. Confirms the earlier bakeoff routing rule (real-repo edits go to
  claude-sonnet-5/grok-4.5/grok-composer, not glm/deepseek) extends cleanly
  to test-hardening, not just fix work.

## Groq native (via opencode, `groq/*` using `GROQ_API_KEY`)

- 2026-07-10 — lane-setup attempts (gpt-oss-120b, gpt-oss-20b,
  llama-3.3-70b-versatile): NOT VIABLE on Groq's free `on_demand` tier,
  skipped per user. Root cause is a throughput floor, not the model or
  key: opencode's per-request footprint (system prompt + tool defs +
  output budget) is ~15k tokens even for a trivial probe, but free-tier
  TPM caps are 8000 (gpt-oss) to 12000 (llama-3.3-70b). Capping output via
  opencode config (`provider.groq.models.<id>.limit.{context,output}`)
  dropped requests from ~39k to ~8–15k but still over the cap, and
  opencode retries the 413 into a throttle death-spiral until timeout.
  Groq as a Ringer worker lane requires the paid Dev tier (higher TPM).
  Config override reverted since the lane is skipped.

## claude-fable-5 (via opencode, `openrouter/anthropic/claude-fable-5`)

- 2026-07-13/14 — real-repo edit probe: same throwaway single-file crate +
  hidden 13-case grader as the ROUND 3 iteration-tree bakeoff (`build_order`
  + `TreeError`, BFS semantics, exact signatures given in full). **PASS,
  attempt 2** (65.5k tok, 326s). Attempt 1 engaged fully — wrote real code,
  ran real tests, self-reported "10 tests pass" — but HALLUCINATED that the
  spec was truncated ("Your message cut off after the scaffold description")
  even though the exact signatures/semantics were present in full, and
  improvised different semantics (ancestor-chain ordering, differently-shaped
  `TreeError`) instead of using the given contract. Attempt 2, with the
  grader's failure injected, re-read the same spec correctly and matched it
  exactly — confirmed against the exported patch (real BFS/VecDeque
  traversal, correct variant shapes). ROUTING NOTE: distinct failure mode
  from glm/deepseek's freeze-and-ask — Fable doesn't refuse, it confidently
  substitutes its own spec. Don't trust attempt-1 output against an exact
  contract without checking it actually used the given signatures, even when
  the model's own summary claims full test coverage.
- Slug correction: the bare alias `openrouter/anthropic/claude-fable`
  (no version) 400s instantly via OpenCode (`UnknownError`, 0 tokens) — the
  real OpenRouter catalog id is `anthropic/claude-fable-5`. Same lesson
  applies to `claude-opus` below.

## claude-opus-4.8 (via opencode, `openrouter/anthropic/claude-opus-4.8`)

- 2026-07-13/14 — same real-repo edit probe as claude-fable-5 above, run in
  parallel: **PASS, attempt 2** (61.5k tok, 272s). Identical failure mode to
  Fable on attempt 1 — spontaneously declared the (complete, untruncated)
  spec "truncated" and substituted its own ordering/error-shape design
  rather than the exact contract given; corrected on the retry once the
  grader's failure was injected. Confirmed against the exported patch (real
  BFS traversal with a HashMap/HashSet/VecDeque implementation, exact
  `TreeError` variant shapes). Bare alias `openrouter/anthropic/claude-opus`
  (no version) fails identically to Fable's bare alias — use
  `anthropic/claude-opus-4.8`.

## grok-4.5 (via opencode, `openrouter/x-ai/grok-4.5`)

- 2026-07-10 — lane-setup probe (write nthprime.py, check executes it):
  PASS attempt 1, 17s, 8.8k tokens. Routed through the funded OpenRouter
  credential ($2/$6 per M). Spot-checked artifact: real trial-division
  nth-prime loop, not hardcoded. Distinct lane from the plan-billed Grok
  Build CLI (`[engines.grok]`, grok-composer-2.5-fast) — this is
  pay-per-token access to xAI's grok-4.x reasoning models via OpenRouter.

## qwen3-next-80b (via opencode, `openrouter/qwen/qwen3-next-80b-a3b-instruct:free`)

- 2026-07-12 — lane-setup probe (write nthfib.py, check executes it): PASS
  attempt 2, 195.5s, 17.9k tokens, $0. Attempt 1 failed not on the algorithm
  but on tool use: the model answered conversationally with the code in a
  fenced markdown block instead of calling the `write` tool, so no file was
  created and the check correctly failed. Attempt 2 (retry with the failure
  injected) called `write` and produced a correct iterative loop (not a
  hardcoded constant). Audition-worthy but watch first-attempt tool-call
  discipline on plain write tasks before trusting it in an unattended batch.
- 2026-07-12/13 — full 5-surface PIPL-arch code-review audition (review-swarm
  contract, real repo, max_parallel 2, ~30 min): **0/5 PASS — all 5 TIMEOUT**
  at the 900s×2 budget (19.5k–71.8k tokens burned per surface before the
  kill). One surface (`telemetry-consumer`) left behind a `report.md` that
  actually satisfied the review contract when checked after the fact, so the
  model CAN produce evidence-cited, correctly-structured findings on real
  repo code — but never finished inside budget on any of the 5 attempts.
  WORSE: the `sip-core` worker on one attempt wrote its `report.md` directly
  into the real repo (`services/sip-core/src/report.md`) instead of its task
  directory — a boundary violation on a spec that explicitly says "never
  modify/create anything in that repo." Combined verdict: this model is a
  genuine serving/throughput casualty on long multi-file real-repo review
  work (same family of failure as qwen3-coder:free and nemotron-3-ultra
  above), AND it does not reliably respect output-location boundaries under
  real-repo exploration the way the trivial single-file probe suggested.
  Do not route qwen3-next-80b:free at unattended real-repo review work;
  a short mechanical write-and-verify task is still fine.

## Small / flash-class models

- First to choke on long conversational or multi-turn harness tasks —
  watch retry counts before scaling them into a batch (2026-07-05 focus
  group lesson).

## Bakeoff — six-lane code ranking (2026-07-10)

- Ran the same 4 algorithmic scenarios (Roman numerals, base-N conversion,
  JSON-path getter, longest-valid-parentheses) across all six lanes, each
  graded by executing the artifact against fixed cases with a no-cheat
  guard. Result: ALL SIX lanes 4/4 first-try. Correctness did not
  differentiate at this difficulty — every lane writes correct,
  well-structured code for clearly-specced algorithmic tasks. So route on
  cost/speed here, not quality. Ranking by ~$/task (blended (in+out)/2 ×
  observed tokens): deepseek-v4-flash ($0.0013, cheapest) < deepseek-v4-pro
  ($0.0065) < glm-5.2 ($0.013) < grok-4.5 ($0.038) < claude-sonnet-5
  ($0.084, ~50% more tokens than the cheap lanes). Fastest avg/task:
  grok-4.5 28s, deepseek-flash 35s, grok-composer 40s (plan-billed, no
  token count), glm 41s, deepseek-pro 44s (jsonpath was a 76s outlier),
  claude 49s. TAKEAWAY: for specced algorithmic code, the cheap lanes
  (flash/pro/glm) are the rational default; reserve claude/grok-4.5 for
  tasks hard or fuzzy enough that quality actually separates — this set
  wasn't. A harder/vaguer scenario set would be needed to find quality gaps.

## Bakeoff — hard real-repo task, first real separation (2026-07-10)

- Task: implement `build_order` + `TreeError` (deterministic BFS over an
  iteration tree with duplicate/missing-parent/cycle detection and strict
  error precedence) in the REAL PIPL-arch `pipl-core` Rust crate, each lane
  in an isolated git worktree, verified by injecting a 13-case grader and
  running `cargo test -p pipl-core`. This finally separated the lanes:
  - PASSED (correct, idiomatic — spot-checked the exported patches):
    claude-sonnet-5 (46.5k tok, 225s), grok-4.5 (37.2k tok, 117s — fastest),
    grok-composer-2.5 (plan-billed, 266s). Claude & grok-4.5 essentially
    matched the reference algorithm.
  - FAILED: glm-5.2, deepseek-v4-pro, deepseek-v4-flash. CRUCIAL NUANCE —
    they did NOT get the algorithm wrong; they made ZERO write/edit tool
    calls. They read the crate, ran `cargo test` (saw existing tests pass),
    and stopped without ever writing iteration_tree.rs. glm's final message:
    "the crate builds/tests pass cleanly, but I don't…"; its reasoning kept
    circling "outside"/"scope". They froze on the spec's tight boundary
    language ("do NOT modify anything outside crates/pipl-core/src", "do not
    commit", etc.) rather than executing the in-scope edit.
  - HONEST READ: on a real-repo multi-file edit under tight guardrails, the
    frontier lanes (Claude, grok-4.5) and grok-composer execute; the cheap
    lanes froze. That is a real capability signal for real work, but it is
    NOT evidence the cheap models can't write the algorithm — untested,
    since they never attempted the edit. Contrast the earlier toy bakeoffs
    where all six wrote correct code first-try: the differentiator here was
    navigating a real repo under constraints, not algorithmic skill.
- SPEC-FRAMING LESSON: heavy prohibition language freezes cautious/cheaper
  models. For real-repo tasks, lead with the affirmative in-scope action
  ("CREATE this file, ADD these two lines — that IS your allowed edit")
  before the boundaries, or the guardrails read as "touch nothing."

- ROUND 2 (2026-07-10): re-ran the 3 failing lanes with maximally
  affirmative framing ("you MUST create this file / add these two lines").
  Still 0/3 — but the cause was NOT spec caution and NOT the algorithm:
  deepseek-v4-pro engaged hard (63k tok / 500s) but ran a WHOLE-WORKSPACE
  cargo build, hit `aws-lc-sys` (the AWS crypto C build) failing in this
  environment, and thrashed on that unrelated error — only 1 edit call, the
  module file never created. glm-5.2 and deepseek-v4-flash stayed low-token
  (froze again). NET: on THIS real repo (large workspace + a partially
  broken aws-lc-sys build + module wiring), the cheap lanes cannot land
  compilable code while Claude/grok-4.5/grok-composer can — a real
  execution/navigation signal. But pure ALGORITHM quality for glm/deepseek
  is STILL untested: they never produced gradeable code. To isolate it,
  run a minimal scaffold crate (just the IterationEdge type + a stub, no
  workspace, no aws-lc-sys) so the only variable is writing build_order.
  Task lesson: scope worker build/verify commands explicitly to
  `-p <crate>` so a broken sibling crate can't derail them.

- ROUND 3 — DEFINITIVE ROOT CAUSE (2026-07-10): stripped ALL repo friction
  — a throwaway single-file crate (`IterationEdge` + a stub, one dep, no
  workspace, no aws-lc-sys, no module wiring), task = add build_order +
  TreeError to src/lib.rs. Result unchanged: claude-sonnet-5, grok-4.5,
  grok-composer PASS; glm-5.2, deepseek-v4-pro, deepseek-v4-flash FAIL,
  each ~9k tokens / ~40s, only read/bash calls, src/lib.rs left as the
  untouched stub. Their final messages are the smoking gun — glm: "Awaiting
  the spec for build_order"; deepseek-flash: "what should TreeError and
  build_order look like?"; deepseek-pro ended its turn after reads. They
  HALT TO ASK FOR A SPEC THAT IS ALREADY IN THE PROMPT, ending the turn
  conversationally; under opencode `--auto` (non-interactive) that closes
  the session with nothing written. So the three "failures" across all
  rounds are an AGENTIC-AUTONOMY failure (bail out and await input on a
  multi-step repo-edit task), NOT algorithm, spec-framing, or repo size.
  Corroborates the flash-class note below. Their pure algorithm skill is
  already known-good from the earlier atomic bakeoffs (all six wrote
  correct code first-try when the task was "write ONE new file from
  scratch"); they specifically choke when the task is "read an existing
  repo, then edit it." ROUTING RULE: for autonomous multi-step repo edits
  via opencode, use claude-sonnet-5 / grok-4.5 / grok-composer; glm and
  deepseek are reliable only on atomic single-file/self-contained tasks.

## Process lessons (cross-model)

- 2026-07-13 — SIX-ATTEMPT SAGA on one fix-swarm task (deltas-hash-coverage),
  every failure a different infrastructure issue, none a model problem: (1-3)
  the background run got killed externally three times in a row (once after
  30+ min on a cold multi-crate build, twice within ~3 min even after
  reducing to serial execution) — cause never fully identified, but pointing
  CARGO_TARGET_DIR at the real repo's already-warm target/ dir (instead of
  each worktree cold-compiling ~60 aws-sdk/crypto crates from scratch) and
  running in the FOREGROUND instead of backgrounded made the next attempt
  finish in 75s instead of 30+ min — do this by default for any worktree
  task in a heavy-dependency crate. (4) a real, reusable harness bug: the
  spec text contained literal `format!("{id}|{verdict}|...")` examples with
  bare `|` characters inside backticks; opencode.cmd's Windows batch
  argument-forwarding re-interpreted the `|` as a cmd.exe PIPE OPERATOR,
  splitting the command mid-argument and leaving a bare `{verdict}` that
  cmd.exe tried to execute as a program name (`'{verdict}' is not
  recognized...`, rc=255) — a spec with zero output produced. LESSON: never
  put literal shell metacharacters (`|`, backticks, `&`, redirects) inside a
  spec's example code on Windows; describe the format in prose ("joined
  with a delimiter character") instead of a literal format-string example.
  (5) switched engine to grok (grok-composer-2.5-fast) after OpenRouter
  credits ran out mid-session for claude-sonnet-5 (a 402 on request, not a
  model failure) — the grok CLI genuinely fixed the code correctly, but
  left its own `terminals/{1,2,3,4}.txt` + `.next-id` session-transcript
  files in the worktree's cwd, which `git add -A` swept into the exported
  patch and tripped the ownership check. LESSON: grok-engine worktree tasks
  need `terminals/` (or wherever this CLI writes session logs) added to the
  ownership exclusion / gitignore before export, the same way opencode
  tasks need care around gitignored build dirs. The actual code fix was
  correct on the very first grok attempt once the pipe-character spec bug
  was gone — extracted by hand from the worktree's staged diff (excluding
  `terminals/`) rather than re-running the swarm a 7th time.
- 2026-07-12/13 — FIRST BLUEPRINT-KIT AUDITIONS (test-hardening, doc-swarm):
  every recorded FAIL across both kits' first real-repo runs was an
  orchestrator check-craft bug, not a model quality problem — exactly what
  "Blueprint — adapt with care" warns about. Fixed, permanent lessons:
  (1) never nest a single-quoted sub-string (e.g. `grep -c ': test$'`) inside
  a `--flag '...'` value that is itself single-quoted — the inner `'`
  prematurely closes the outer quote and silently splits argv, producing
  a baffling "unrecognized arguments" error far from the real cause; use
  double quotes for the inner string instead. (2) `test_hardening_check.py`'s
  `run_tests()` called `subprocess.run(command, shell=True)`, which on
  Windows resolves to cmd.exe and chokes on bash constructs like `export`
  and `$(...)` — fixed to route through `bash -c` on Windows explicitly,
  the same pattern `ringer.py`'s own `_run_check` already uses. This is a
  permanent fix to `templates/test-hardening/checks/test_hardening_check.py`,
  not a per-run workaround. (3) an assertion-counting regex
  `\b(assert_eq!|assert_ne!|assert!)\b` had a trailing `\b` immediately after
  `!`, but real call sites are followed by `(` — a non-word char — so the
  boundary never matched and every file undercounted to zero assertions;
  drop the trailing `\b`. (4) doc-swarm's symbol-existence check treats
  EVERY backtick span inside the Documented Symbols section as a claimed
  source symbol requiring a literal grep match — so a spec that tells
  workers to backtick both the symbol AND its `file.rs:42` citation on the
  same line poisons the check with citations that obviously don't appear
  verbatim in source. Keep citations as plain unbacktracked parenthetical
  text in that section. Rust also never spells a `Type::method` qualified
  path at its definition site, so require bare identifiers only (`submit`,
  not `Mirror::submit`); use `--symbol-allowlist` for legitimately
  non-literal terms (HTTP headers, AWS API names, URI templates) instead of
  fighting the model's natural tendency to reference them. (5) doc-swarm's
  per-example runnable-code check has a hard-coded 60s timeout; a spec that
  doesn't forbid a second, slower fenced block (e.g. a full `cargo test` run
  instead of `--list`) will eventually blow it on a cold build. (6) a global
  `--min-section-words` floor applied uniformly to every required section
  cannot coexist with a spec that also asks for a single-command Examples
  section or a one-word "None" Assumptions section — either lower the floor
  or require a full sentence even for the "none" case; don't leave the two
  instructions contradicting each other.
- 2026-07-12/13 — WORKTREE REUSE AFTER A FAILED TASK (operational gotcha,
  Windows). A task that fails (not passes) leaves its worktree registered;
  re-running a manifest with the same `workdir`/task keys tries to create a
  new worktree at the same already-registered path and errors at the harness
  level before the worker even starts (0 tokens, 0s elapsed, empty log).
  `git worktree remove --force` can itself fail with "Permission denied" on
  Windows if something still holds a handle inside `.git/worktrees/<name>`
  (observed here with no obviously-related process running). Cheapest fix:
  point the retry at a fresh `workdir` rather than fight the lock.
- 2026-07-10 — READ-MODEL STALENESS after hand-editing the eval log
  (operational gotcha). `./ringer.py models` reads the derived SQLite
  `ringer.db`, which syncs from `runs.jsonl` INCREMENTALLY via a byte
  cursor. Deleting rows from the MIDDLE of the JSONL (e.g. a purge) shifts
  every later byte, so the cursor-based sync leaves the read model stale —
  the scoreboard keeps showing purged rows. FIX: run `./ringer.py db
  rebuild` after any manual edit to runs.jsonl to drop and re-materialize
  the DB from source. Applies to every purge in this file — after editing
  the JSONL, always `db rebuild` and re-verify before trusting the board.

- 2026-07-10 — purged the 2 check-bug claude-sonnet-5 bakeoff rows (the
  grader false-negative below; backup `runs.jsonl.bak-20260710-claudebakeoff`)
  and ran `db rebuild`. Claude's bakeoff record is now a clean 4/4.

- 2026-07-10 — GRADER FALSE-NEGATIVE (check bug, fixed). First six-lane
  bakeoff failed claude-sonnet-5 0/1 while the other five passed. Root
  cause was the grader, not the model: a `re.findall(r'\b(eval|exec|
  compile|__import__)\b', src)` no-cheat guard matched those words inside
  claude's own docstring ("no use of eval/exec/compile…"). Claude's parser
  was correct. Fix: tokenizer-based guard that flags only real NAME usage
  of the banned builtins, ignoring comments/strings and attribute access
  (re.compile is fine). Re-ran under the fixed guard: claude 4/4. Lesson —
  a text-grep for banned tokens punishes models that DOCUMENT their
  compliance; scan code structure (tokenize/AST), not raw source text.


- 2026-07-10 — EVAL-LOG PURGE (Windows machine, user-authorized). Removed
  19 non-PASS rows from `~/.ringer/runs.jsonl` (backup:
  `runs.jsonl.bak-20260710-prepurge`) after verifying every one was an
  infrastructure/account/harness failure, never a model producing a wrong
  answer: 9 `ringer-demo` smoke-test rows (which tripped the pre-fix
  Windows cmd.exe/bash `_run_check` bug — `'{' is not recognized` — and
  made codex look 0/6), plus 10 probe fails from pre-funding OpenRouter
  402s, a provider max_tokens cap (Venice 16384 < opencode's 32000 request
  on llama-3.3-70b:free), and opencode writing artifacts to absolute paths
  on Windows. Rows where the model never received the request or never
  produced judgeable output are not model-performance data; keeping them
  mislabels account/harness problems as model failures and poisons every
  routing call. Board went 26→7 rows, all genuine passes. Distinction from
  the annotate-don't-delete norm below: that norm covers FAILs where the
  model DID produce correct work a buggy check misjudged — those get
  annotated and re-run; these rows had no model datum at all.

- 2026-07-10 — SECOND EVAL-LOG PURGE (user-authorized). Removed 16 more
  non-PASS rows from the Claude/Groq lane-setup attempts (backup:
  `runs.jsonl.bak-20260710-purge2`), all infrastructure: Groq free-tier
  TPM throttles (8×gpt-oss-120b, 2×llama-3.3-70b, 2×timeout) and 4 native
  `anthropic/claude-sonnet-5` 401s from the OAuth-token-in-env issue. Board
  back to 8 rows, all genuine passes. Same rule as above: no model datum,
  so not model-performance data.

- 2026-07-06 — the orchestrator's CHECKS were the day's top failure source:
  three check bugs (fixture newline join, first-occurrence ordering vs the
  watchlist strip, claim-prefix split on '.' instead of ':') each produced
  a FAIL verdict on work that was actually correct — including all four
  capability-research packets at once. Every one was caught by reading raw
  logs/artifacts before blaming the model. Corollary for the scoreboard:
  recorded FAILs whose root cause was a check bug are annotated here, and
  check fixtures deserve the same review care as production code.


- 2026-07-06 — HARNESS BUG (fix in flight on feat/model-perf-log):
  Verifier.verify evaluated expect_files BEFORE running the check, so any
  check that itself creates/exports its deliverable (the worktree
  patch-export pattern) failed attempt 1 with "missing expected files" even
  when the check printed PASS. Cost 3 phantom retries in one run — and it
  poisons first_try_pass_rate, the model log's routing signal. Until the
  reorder lands on your checkout: have the WORKER write the declared
  deliverable, or don't declare check-created files in expect_files. When
  reading seeded scoreboard numbers, remember 2026-07-06 first-try rates
  are depressed by this.
- 2026-07-06 — the model log is now automatic: every attempt row carries
  model/task_type/retry; `./ringer.py models` prints the scoreboard; 81
  historical rows were seeded via scripts/backfill_model_log.py with a
  hand-authored task-type mapping. Give every manifest task a task_type or
  its evidence buckets as (untyped).

- 2026-07-06 — a three-model "bakeoff" ran every task on the engine's
  hard-coded model: task keys said glm/gpt/kimi, but the opencode engine
  block pinned glm-5.2, so one model wrote all three "competing" reviews.
  This is why the per-task `model` field exists — a bakeoff is only a
  bakeoff if the manifest, not the engine block, names the model. Verify
  with the `model` column in the run state, not the task key.
- 2026-07-06 — spawning 5-6 opencode workers simultaneously hit opencode's
  local "database is locked" (sqlite) — several instant attempt-1 failures,
  all absorbed by Ringer's retry. Cosmetic in Ringside ("sent back" at 0s) but
  wastes an attempt; consider staggering opencode spawns.
- 2026-07-06 — opencode's bash tool kills foreground commands around the
  ~2-minute mark: a 2min+ image-generation API call can never finish inline.
  Spec pattern that works: nohup the long command in the background, then
  poll for the output file in separate short commands.
- 2026-07-06 — two check-craft lessons from the same run: (1) URL-allowlist
  checks must be prefix-tolerant (workers legitimately trim slugs); (2) any
  heading-regex must tolerate numbered headings ("## 3. Type / Typography").
  Both failures looked like worker laziness until the raw logs said otherwise.
- 2026-07-06 — elsas-website demo, check-craft in BOTH directions: (1) a fixed
  800-char body floor failed a worker for faithfully converting genuinely tiny
  source posts — floor must scale with the source; (2) a citation gate treating
  every backtick as a page-quote failed honest reviewers who backticked their
  own fix-suggestions — line-scoped pair parsing + attribute-aware corpus fixed
  it; (3) needle-exception lists must be shared across ALL checks that consume
  the needle set (a needle excepted in one checker failed a task through
  another). Post-mortems ruled FOR the worker 3 times this run — read raw logs
  before blaming the model.
- 2026-07-06 — opencode sqlite "database is locked" again with just 2
  simultaneous opencode spawns (page-news + page-about-faq); retry absorbed it.

## codex (2026-07-06, bench-operator-proofing)
- 8/8 code-feature tasks passed attempt 1 across 3 rounds (worktrees mode, Python harness refactor; 108k-406k tokens/task). Specs embedded the approved architecture doc + exact file ownership; checks built fresh uv venvs and ran the full pytest suite.
- Lesson (check design, not model): all 3 post-integration bugs were invisible to the checks — a test that passed only because the worker's worktree lacked .env, a `--help`-only assertion missing a runtime importlib/sys.modules bug (py3.12 dataclasses), and bare console-script names failing outside activated venvs. Checks should exercise one real invocation from a cold shell, not just --help.

## gpt-5.6-sol (codex)
- 2026-07-09 code-feature/code-fix (ringside-overhaul): 4/4 first-try — a ringer.py logging change with tests, a 265-line stdlib backfill CLI (atomic rewrite, dry-run, idempotence all check-verified), a ~1500-line single-file HTML redesign (running-now pills + worker-card grid + multi-expansion refactor, 30KB patch, node --check + contract greps + unittest), and a render-gating change where it correctly UPDATED tests asserting the old behavior instead of gaming the check. Medium/high reasoning, 65–120k tokens/task.
- Same day, different session (bench-harness-patches, code-fix): 0.29 first-try over 7 tasks on a Next.js/Turbopack harness. Spec and check quality dominate model choice — see the scoreboard before generalizing either number.

## GPT-5.5 (codex) — attribution caveat
- Scoreboard rows dated before 2026-07-09 may actually be gpt-5.6: codex eval rows logged model="" until the write-time stamping fix (PR #18) and were credited to GPT-5.5 by the registry default at read time, while the machine's codex default had already moved to gpt-5.6-sol at an unknown earlier date. `scripts/backfill_model_from_logs.py` re-stamps rows with surviving command-log evidence; anything it skips is a mixed-model aggregate. Trust post-2026-07-09 rows.
