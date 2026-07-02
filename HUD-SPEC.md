# SwarmHUD — native floating mission-control widget for swarm.py

Build a tiny native macOS HUD app at `/Users/jonathanedwards/fleet/swarm/SwarmHUD.app`, compiled with `swiftc` from a single `SwarmHUD.swift` in this directory (no Xcode project). Swift 6.3 / CLT toolchain, target arm64 macOS.

## Window
- Borderless floating `NSPanel`: `.nonactivatingPanel`, window level `.floating` (always on top), `collectionBehavior` includes `.canJoinAllSpaces` (visible on every Space/desktop).
- Compact: ~360×420 default, user-resizable within 280×220 … 600×900, size+position persisted in UserDefaults across launches.
- Draggable by its whole background (`isMovableByWindowBackground = true`).
- Dark translucent chrome: rounded 14pt corners, `NSVisualEffectView` (.hudWindow material) behind content.
- Tiny top bar: colored dot (status: gray idle / cyan running / green all-pass / red failures) + run name + close (⨯) and collapse (–) text buttons. Collapse shrinks to just the top bar (a true mini strip).
- ESC or ⨯ hides the window (app keeps running in menu bar).

## Menu bar presence
- `NSStatusItem` with a simple swarm glyph (use an SF Symbol e.g. "circle.hexagongrid.fill"). Click toggles the HUD. Menu: Show/Hide HUD, Quit.
- App is `LSUIElement` (no Dock icon).

## Content
- A `WKWebView` filling the panel below the top bar, loading `http://localhost:8787/` (the swarm.py dashboard — it already looks the part).
- Poll `http://localhost:8787/state.json` every 2s from Swift (URLSession) to drive the top-bar dot + run name, independent of the webview.
- If the server is unreachable: webview shows a built-in fallback page (inline HTML string: dark bg, subtle pulsing "waiting for swarm…" text) and the dot goes gray. Auto-recovers and reloads when the server reappears. Handle port fallback: try 8787 then 8788.
- App Transport Security: allow localhost HTTP (NSAppTransportSecurity/NSAllowsLocalNetworking in Info.plist).

## Single instance
- Bundle id `com.jonedwards.swarmhud`. On launch, if another instance is running (NSRunningApplication scan), activate it and exit.

## Build & bundle
- Provide `build-hud.sh` in this directory: compiles `swiftc -O SwarmHUD.swift -o SwarmHUD.app/Contents/MacOS/SwarmHUD`, assembles the .app bundle (Contents/Info.plist with CFBundleIdentifier, LSUIElement=true, NSAllowsLocalNetworking, CFBundleName SwarmHUD), `codesign --force --sign - SwarmHUD.app` (ad-hoc), prints DONE.
- Run the script; verify the bundle exists and `codesign -v` passes. Do NOT launch the app (the reviewer will).

## swarm.py integration
Edit swarm.py's browser-open logic (search for the `open` call, ~line 364): if `/Users/jonathanedwards/fleet/swarm/SwarmHUD.app` exists, run `open -a <that app>` (single-instance: relaunches just activate it — no more new tabs); else fall back to the current `open <url>`. Keep a `--browser` CLI flag to force the old browser behavior. Run `python3 -m py_compile swarm.py` after editing.

Reply DONE + one paragraph of design decisions when the bundle is built, signed, and swarm.py is patched + compiles.
