# SwarmHUD v2 amendment — multi-swarm aggregation + fleet identities

Amend the existing SwarmHUD.swift + swarm.py in this directory (built per HUD-SPEC.md). Keep the window/menu-bar/single-instance chassis exactly as-is.

## swarm.py changes
1. Per-run state: write state to `~/.swarm/runs/<run_id>.json` (instead of, or in addition to, the legacy `~/.swarm/state.json` — drop the legacy write). Include new top-level fields: `identity` (see 2), `pid` (os.getpid()), `port` (dashboard port or null), `finished` (bool), `summary` ({pass, fail, tokens} once finished). On graceful exit AND Ctrl-C, write a final state with `finished: true`; leave the file (HUD handles fading). On startup, delete own stale file if re-using a run_id.
2. `--identity <name>` CLI flag; default: env `FLEET_IDENTITY`, else env `SWARM_IDENTITY`, else short hostname. Stamp into state json and into swarm_runs rows (new `orchestrator` value — the column already exists).
3. Keep the per-instance HTTP dashboard as-is (port 8787 with +1,+2… fallback so N instances coexist), but the HUD no longer depends on it.
4. `python3 -m py_compile swarm.py` must pass.

## SwarmHUD.swift changes
1. Drop the localhost URL + state.json polling. New data source: every 1s, read ALL files in `~/.swarm/runs/`, parse JSON. A run is LIVE if `finished==false` AND its pid is alive (kill(pid,0)) AND file mtime < 30s; FINISHED if `finished==true` (show for 60s after mtime, then ignore); DEAD (crashed orchestrator: pid gone, not finished) — show with a distinct "died" state for 5 min.
2. Render natively-driven HTML in the WKWebView via `loadHTMLString` once + `evaluateJavaScript("update(<json>)")` per tick (no server). The page (inline Swift string): dark HUD theme matching the dashboard's look — for EACH swarm a section: header row = pulsing status dot, run name, **identity badge** (rounded chip, deterministic color hashed from identity name — lex/codex-mini/aicred each get a stable distinct color), elapsed, aggregate tokens; under it a tight grid of task chips (key + status color + elapsed; "⤷N" when children>0). Sections sorted: live first (newest top), then finished (dimmed, with final ✓/✗ tally), then died (red-tinged). Empty state: pulsing "no swarms running".
3. Top bar dot aggregates across ALL live swarms (gray none / cyan any-running / green last-run-all-pass / red any-fail). Top bar text: "N swarms · M agents" when multiple live, else run name.
4. Collapsed mini-strip mode shows that same aggregate line — the at-a-glance ticker.
5. Rebuild with build-hud.sh, codesign -v must pass. Do NOT launch the app.

Reply DONE + a paragraph on decisions.
