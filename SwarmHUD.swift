import AppKit
import Darwin
import Foundation
import WebKit

private let bundleIdentifier = "com.jonedwards.swarmhud"
private let defaultPanelSize = NSSize(width: 360, height: 420)
private let minimumPanelSize = NSSize(width: 280, height: 220)
private let maximumPanelSize = NSSize(width: 600, height: 900)
private let topBarHeight: CGFloat = 34
private let frameDefaultsKey = "SwarmHUD.panelFrame"
private let runsDirectory = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent(".swarm", isDirectory: true)
    .appendingPathComponent("runs", isDirectory: true)

private enum SwarmStatus {
    case idle
    case running
    case pass
    case fail

    var color: NSColor {
        switch self {
        case .idle:
            return NSColor(calibratedRed: 0.42, green: 0.46, blue: 0.52, alpha: 1.0)
        case .running:
            return NSColor(calibratedRed: 0.10, green: 0.78, blue: 1.0, alpha: 1.0)
        case .pass:
            return NSColor(calibratedRed: 0.23, green: 0.86, blue: 0.45, alpha: 1.0)
        case .fail:
            return NSColor(calibratedRed: 1.0, green: 0.20, blue: 0.30, alpha: 1.0)
        }
    }
}

private enum RunDisplayState: String {
    case live
    case finished
    case died

    var sortRank: Int {
        switch self {
        case .live:
            return 0
        case .finished:
            return 1
        case .died:
            return 2
        }
    }
}

private struct TaskSnapshot {
    let key: String
    let status: String
    let elapsedS: Double
    let tokens: Int
    let children: Int

    static func parse(_ raw: [String: Any]) -> TaskSnapshot? {
        let key = stringValue(raw["key"])?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let key, !key.isEmpty else {
            return nil
        }
        return TaskSnapshot(
            key: key,
            status: stringValue(raw["status"]) ?? "queued",
            elapsedS: doubleValue(raw["elapsed_s"]) ?? 0,
            tokens: intValue(raw["tokens"]) ?? 0,
            children: intValue(raw["children"]) ?? 0
        )
    }

    func payload() -> [String: Any] {
        return [
            "key": key,
            "status": status,
            "elapsed_s": elapsedS,
            "tokens": tokens,
            "children": children
        ]
    }
}

private struct RunTotals {
    let running: Int
    let done: Int
    let pass: Int
    let fail: Int
    let tokens: Int

    static let empty = RunTotals(running: 0, done: 0, pass: 0, fail: 0, tokens: 0)

    static func parse(_ raw: [String: Any]?) -> RunTotals {
        guard let raw else {
            return .empty
        }
        return RunTotals(
            running: intValue(raw["running"]) ?? 0,
            done: intValue(raw["done"]) ?? 0,
            pass: intValue(raw["pass"]) ?? 0,
            fail: intValue(raw["fail"]) ?? 0,
            tokens: intValue(raw["tokens"]) ?? 0
        )
    }

    func payload() -> [String: Any] {
        return [
            "running": running,
            "done": done,
            "pass": pass,
            "fail": fail,
            "tokens": tokens
        ]
    }
}

private struct RunSummary {
    let pass: Int
    let fail: Int
    let tokens: Int

    static func parse(_ raw: [String: Any]?) -> RunSummary? {
        guard let raw else {
            return nil
        }
        return RunSummary(
            pass: intValue(raw["pass"]) ?? 0,
            fail: intValue(raw["fail"]) ?? 0,
            tokens: intValue(raw["tokens"]) ?? 0
        )
    }

    func payload() -> [String: Any] {
        return [
            "pass": pass,
            "fail": fail,
            "tokens": tokens
        ]
    }
}

private struct SwarmRun {
    let runID: String
    let runName: String
    let identity: String
    let pid: Int?
    let port: Int?
    let finished: Bool
    let startedAtRaw: String?
    let startedAt: Date?
    let modifiedAt: Date
    let state: RunDisplayState
    let tasks: [TaskSnapshot]
    let totals: RunTotals
    let summary: RunSummary?

    var passCount: Int {
        return summary?.pass ?? totals.pass
    }

    var failCount: Int {
        return summary?.fail ?? totals.fail
    }

    var tokenCount: Int {
        return summary?.tokens ?? totals.tokens
    }

    var sortDate: Date {
        return startedAt ?? modifiedAt
    }

    static func parse(fileURL: URL, now: Date) -> SwarmRun? {
        guard
            let data = try? Data(contentsOf: fileURL),
            let object = try? JSONSerialization.jsonObject(with: data),
            let root = object as? [String: Any]
        else {
            return nil
        }

        let values = try? fileURL.resourceValues(forKeys: [.contentModificationDateKey])
        let modifiedAt = values?.contentModificationDate ?? Date.distantPast
        let age = now.timeIntervalSince(modifiedAt)
        let finished = boolValue(root["finished"]) ?? false
        let pid = intValue(root["pid"])
        let pidAlive = pid.map(processIsAlive) ?? false
        let state: RunDisplayState

        if finished {
            guard age <= 60 else {
                return nil
            }
            state = .finished
        } else if pidAlive && age <= 30 {
            state = .live
        } else {
            guard age <= 300 else {
                return nil
            }
            state = .died
        }

        let runID = stringValue(root["run_id"])
            ?? fileURL.deletingPathExtension().lastPathComponent
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let runName = stringValue(root["run_name"])?.trimmingCharacters(in: .whitespacesAndNewlines)
        let identity = stringValue(root["identity"])?.trimmingCharacters(in: .whitespacesAndNewlines)
        let startedAtRaw = stringValue(root["started_at"])
        let taskObjects = root["tasks"] as? [[String: Any]] ?? []
        let tasks = taskObjects.compactMap(TaskSnapshot.parse)

        return SwarmRun(
            runID: runID.isEmpty ? "swarm" : runID,
            runName: runName?.isEmpty == false ? runName! : "swarm",
            identity: identity?.isEmpty == false ? identity! : "unknown",
            pid: pid,
            port: intValue(root["port"]),
            finished: finished,
            startedAtRaw: startedAtRaw,
            startedAt: parseISODate(startedAtRaw),
            modifiedAt: modifiedAt,
            state: state,
            tasks: tasks,
            totals: RunTotals.parse(root["totals"] as? [String: Any]),
            summary: RunSummary.parse(root["summary"] as? [String: Any])
        )
    }

    func elapsedSeconds(now: Date) -> Double {
        let taskElapsed = tasks.map(\.elapsedS).max() ?? 0
        if state == .live, let startedAt {
            return max(taskElapsed, now.timeIntervalSince(startedAt))
        }
        return taskElapsed
    }

    func payload(now: Date) -> [String: Any] {
        var payload: [String: Any] = [
            "run_id": runID,
            "run_name": runName,
            "identity": identity,
            "state": state.rawValue,
            "finished": finished,
            "started_at": startedAtRaw ?? "",
            "mtime": modifiedAt.timeIntervalSince1970,
            "elapsed_s": elapsedSeconds(now: now),
            "tasks": tasks.map { $0.payload() },
            "totals": totals.payload(),
            "pass": passCount,
            "fail": failCount,
            "tokens": tokenCount
        ]
        payload["pid"] = pid.map { $0 as Any } ?? NSNull()
        payload["port"] = port.map { $0 as Any } ?? NSNull()
        if let summary {
            payload["summary"] = summary.payload()
        }
        return payload
    }

    private static func processIsAlive(_ pid: Int) -> Bool {
        guard pid > 0 else {
            return false
        }
        return Darwin.kill(pid_t(pid), 0) == 0
    }
}

private struct AggregateSnapshot {
    let status: SwarmStatus
    let title: String
}

private final class StatusDotView: NSView {
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.cornerRadius = 5
        layer?.backgroundColor = SwarmStatus.idle.color.cgColor
        layer?.shadowColor = NSColor.black.cgColor
        layer?.shadowOpacity = 0.28
        layer?.shadowRadius = 2
        layer?.shadowOffset = .zero
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setStatus(_ status: SwarmStatus) {
        layer?.backgroundColor = status.color.cgColor
        layer?.shadowColor = status.color.withAlphaComponent(0.75).cgColor
        layer?.shadowOpacity = status == .idle ? 0.20 : 0.55
    }
}

private final class HUDPanel: NSPanel {
    var cancelHandler: (() -> Void)?

    override var canBecomeKey: Bool {
        return true
    }

    override var canBecomeMain: Bool {
        return false
    }

    override func cancelOperation(_ sender: Any?) {
        cancelHandler?()
    }
}

private final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    private var statusItem: NSStatusItem!
    private var statusMenu: NSMenu!
    private var panel: HUDPanel!
    private var rootView: NSVisualEffectView!
    private var dotView: StatusDotView!
    private var runNameLabel: NSTextField!
    private var contentContainer: NSView!
    private var webView: WKWebView!
    private var pollTimer: Timer?
    private var pageLoaded = false
    private var pendingScript: String?
    private var isCollapsed = false
    private var expandedFrame: NSRect?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if activateExistingInstanceIfNeeded() {
            NSApp.terminate(nil)
            return
        }

        NSApp.setActivationPolicy(.accessory)
        buildPanel()
        buildStatusItem()
        showHUD()
        startPolling()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showHUD()
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        saveExpandedFrame()
    }

    private func activateExistingInstanceIfNeeded() -> Bool {
        let currentPid = ProcessInfo.processInfo.processIdentifier
        let otherInstance = NSWorkspace.shared.runningApplications.first { app in
            app.bundleIdentifier == bundleIdentifier && app.processIdentifier != currentPid
        }

        if let otherInstance {
            otherInstance.activate(options: [])
            return true
        }

        return false
    }

    private func buildPanel() {
        let frame = loadSavedFrame()
        panel = HUDPanel(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel, .resizable],
            backing: .buffered,
            defer: false
        )
        panel.delegate = self
        panel.cancelHandler = { [weak self] in
            self?.hideHUD()
        }
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.minSize = minimumPanelSize
        panel.maxSize = maximumPanelSize
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true

        rootView = NSVisualEffectView(frame: .zero)
        rootView.translatesAutoresizingMaskIntoConstraints = false
        rootView.material = .hudWindow
        rootView.blendingMode = .behindWindow
        rootView.state = .active
        rootView.wantsLayer = true
        rootView.layer?.cornerRadius = 14
        rootView.layer?.masksToBounds = true
        panel.contentView = rootView

        let topBar = makeTopBar()
        contentContainer = NSView(frame: .zero)
        contentContainer.translatesAutoresizingMaskIntoConstraints = false
        contentContainer.wantsLayer = true
        contentContainer.layer?.backgroundColor = NSColor(calibratedWhite: 0.02, alpha: 0.32).cgColor

        webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.navigationDelegate = self
        webView.allowsMagnification = false
        contentContainer.addSubview(webView)

        rootView.addSubview(topBar)
        rootView.addSubview(contentContainer)

        NSLayoutConstraint.activate([
            topBar.topAnchor.constraint(equalTo: rootView.topAnchor),
            topBar.leadingAnchor.constraint(equalTo: rootView.leadingAnchor),
            topBar.trailingAnchor.constraint(equalTo: rootView.trailingAnchor),
            topBar.heightAnchor.constraint(equalToConstant: topBarHeight),

            contentContainer.topAnchor.constraint(equalTo: topBar.bottomAnchor),
            contentContainer.leadingAnchor.constraint(equalTo: rootView.leadingAnchor),
            contentContainer.trailingAnchor.constraint(equalTo: rootView.trailingAnchor),
            contentContainer.bottomAnchor.constraint(equalTo: rootView.bottomAnchor),

            webView.topAnchor.constraint(equalTo: contentContainer.topAnchor),
            webView.leadingAnchor.constraint(equalTo: contentContainer.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: contentContainer.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: contentContainer.bottomAnchor)
        ])
    }

    private func makeTopBar() -> NSView {
        let topBar = NSView(frame: .zero)
        topBar.translatesAutoresizingMaskIntoConstraints = false
        topBar.wantsLayer = true
        topBar.layer?.backgroundColor = NSColor(calibratedWhite: 0.03, alpha: 0.46).cgColor

        dotView = StatusDotView(frame: .zero)
        dotView.translatesAutoresizingMaskIntoConstraints = false

        runNameLabel = NSTextField(labelWithString: "no swarms running")
        runNameLabel.translatesAutoresizingMaskIntoConstraints = false
        runNameLabel.textColor = NSColor(calibratedWhite: 0.90, alpha: 1.0)
        runNameLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold)
        runNameLabel.lineBreakMode = .byTruncatingTail
        runNameLabel.maximumNumberOfLines = 1

        let collapseButton = makeTopBarButton(title: "–", action: #selector(toggleCollapse))
        let closeButton = makeTopBarButton(title: "⨯", action: #selector(closeHUD))

        topBar.addSubview(dotView)
        topBar.addSubview(runNameLabel)
        topBar.addSubview(collapseButton)
        topBar.addSubview(closeButton)

        NSLayoutConstraint.activate([
            dotView.leadingAnchor.constraint(equalTo: topBar.leadingAnchor, constant: 14),
            dotView.centerYAnchor.constraint(equalTo: topBar.centerYAnchor),
            dotView.widthAnchor.constraint(equalToConstant: 10),
            dotView.heightAnchor.constraint(equalToConstant: 10),

            runNameLabel.leadingAnchor.constraint(equalTo: dotView.trailingAnchor, constant: 9),
            runNameLabel.centerYAnchor.constraint(equalTo: topBar.centerYAnchor),

            collapseButton.leadingAnchor.constraint(greaterThanOrEqualTo: runNameLabel.trailingAnchor, constant: 10),
            collapseButton.trailingAnchor.constraint(equalTo: closeButton.leadingAnchor, constant: -2),
            collapseButton.centerYAnchor.constraint(equalTo: topBar.centerYAnchor),
            collapseButton.widthAnchor.constraint(equalToConstant: 24),
            collapseButton.heightAnchor.constraint(equalToConstant: 24),

            closeButton.trailingAnchor.constraint(equalTo: topBar.trailingAnchor, constant: -8),
            closeButton.centerYAnchor.constraint(equalTo: topBar.centerYAnchor),
            closeButton.widthAnchor.constraint(equalToConstant: 24),
            closeButton.heightAnchor.constraint(equalToConstant: 24)
        ])

        return topBar
    }

    private func makeTopBarButton(title: String, action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.isBordered = false
        button.bezelStyle = .inline
        button.font = NSFont.systemFont(ofSize: 15, weight: .medium)
        button.refusesFirstResponder = true
        button.attributedTitle = NSAttributedString(
            string: title,
            attributes: [
                .foregroundColor: NSColor(calibratedWhite: 0.86, alpha: 1.0),
                .font: NSFont.systemFont(ofSize: 15, weight: .medium)
            ]
        )
        return button
    }

    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "circle.hexagongrid.fill", accessibilityDescription: "SwarmHUD")
            button.imagePosition = .imageOnly
            button.target = self
            button.action = #selector(statusItemClicked(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        statusMenu = NSMenu()
        statusMenu.addItem(NSMenuItem(title: "Show HUD", action: #selector(toggleHUDFromMenu), keyEquivalent: ""))
        statusMenu.addItem(NSMenuItem.separator())
        statusMenu.addItem(NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        for item in statusMenu.items {
            item.target = self
        }
    }

    private func startPolling() {
        webView.loadHTMLString(Self.hudHTML, baseURL: nil)
        pollState()
        pollTimer = Timer(timeInterval: 1.0, target: self, selector: #selector(pollState), userInfo: nil, repeats: true)
        if let pollTimer {
            RunLoop.main.add(pollTimer, forMode: .common)
        }
    }

    @objc private func pollState() {
        let now = Date()
        let runs = loadRuns(now: now)
        let aggregate = aggregateRuns(runs)
        dotView.setStatus(aggregate.status)
        runNameLabel.stringValue = aggregate.title
        updateWebView(runs: runs, now: now)
    }

    private func loadRuns(now: Date) -> [SwarmRun] {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: runsDirectory,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        )) ?? []

        return urls
            .filter { $0.pathExtension.lowercased() == "json" }
            .compactMap { SwarmRun.parse(fileURL: $0, now: now) }
            .sorted { left, right in
                if left.state.sortRank != right.state.sortRank {
                    return left.state.sortRank < right.state.sortRank
                }
                return left.sortDate > right.sortDate
            }
    }

    private func aggregateRuns(_ runs: [SwarmRun]) -> AggregateSnapshot {
        let liveRuns = runs.filter { $0.state == .live }
        let anyFailure = runs.contains { run in
            run.state == .died || run.failCount > 0
        }
        let status: SwarmStatus
        if anyFailure {
            status = .fail
        } else if !liveRuns.isEmpty {
            status = .running
        } else if let newest = runs.first, newest.state == .finished, newest.passCount > 0 {
            status = .pass
        } else {
            status = .idle
        }

        let title: String
        if liveRuns.count > 1 {
            let agents = liveRuns.reduce(0) { $0 + $1.tasks.count }
            title = "\(liveRuns.count) swarms · \(agents) agents"
        } else if let liveRun = liveRuns.first {
            title = liveRun.runName
        } else if let newest = runs.first {
            title = newest.state == .died ? "\(newest.runName) died" : newest.runName
        } else {
            title = "no swarms running"
        }

        return AggregateSnapshot(status: status, title: title)
    }

    private func updateWebView(runs: [SwarmRun], now: Date) {
        let payload: [String: Any] = [
            "runs": runs.map { $0.payload(now: now) }
        ]
        guard
            JSONSerialization.isValidJSONObject(payload),
            let data = try? JSONSerialization.data(withJSONObject: payload, options: []),
            let json = String(data: data, encoding: .utf8)
        else {
            return
        }

        let script = "update(\(json));"
        if pageLoaded {
            webView.evaluateJavaScript(script, completionHandler: nil)
        } else {
            pendingScript = script
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        pageLoaded = true
        if let pendingScript {
            self.pendingScript = nil
            webView.evaluateJavaScript(pendingScript, completionHandler: nil)
        }
    }

    private func showHUD() {
        panel.orderFrontRegardless()
        panel.makeKey()
        updateStatusMenuTitle()
    }

    private func hideHUD() {
        saveExpandedFrame()
        panel.orderOut(nil)
        updateStatusMenuTitle()
    }

    @objc private func closeHUD() {
        hideHUD()
    }

    @objc private func toggleCollapse() {
        if isCollapsed {
            expandPanel()
        } else {
            collapsePanel()
        }
    }

    private func collapsePanel() {
        guard !isCollapsed else {
            return
        }

        expandedFrame = panel.frame
        saveExpandedFrame()
        isCollapsed = true
        contentContainer.isHidden = true
        panel.minSize = NSSize(width: minimumPanelSize.width, height: topBarHeight)

        let oldFrame = panel.frame
        let newFrame = NSRect(
            x: oldFrame.origin.x,
            y: oldFrame.maxY - topBarHeight,
            width: oldFrame.width,
            height: topBarHeight
        )
        panel.setFrame(newFrame, display: true, animate: true)
    }

    private func expandPanel() {
        guard isCollapsed else {
            return
        }

        let oldFrame = panel.frame
        var targetFrame = expandedFrame ?? loadSavedFrame()
        targetFrame.origin.x = oldFrame.origin.x
        targetFrame.origin.y = oldFrame.maxY - targetFrame.height
        if targetFrame.height < minimumPanelSize.height {
            targetFrame.size.height = defaultPanelSize.height
            targetFrame.origin.y = oldFrame.maxY - targetFrame.height
        }
        if targetFrame.width < minimumPanelSize.width {
            targetFrame.size.width = defaultPanelSize.width
        }

        isCollapsed = false
        contentContainer.isHidden = false
        panel.minSize = minimumPanelSize
        panel.setFrame(targetFrame, display: true, animate: true)
        saveExpandedFrame()
    }

    @objc private func statusItemClicked(_ sender: Any?) {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp || event?.modifierFlags.contains(.control) == true {
            showStatusMenu()
            return
        }

        if panel.isVisible {
            hideHUD()
        } else {
            showHUD()
        }
    }

    @objc private func toggleHUDFromMenu() {
        if panel.isVisible {
            hideHUD()
        } else {
            showHUD()
        }
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func showStatusMenu() {
        updateStatusMenuTitle()
        statusItem.menu = statusMenu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    private func updateStatusMenuTitle() {
        statusMenu?.item(at: 0)?.title = panel?.isVisible == true ? "Hide HUD" : "Show HUD"
    }

    func windowDidMove(_ notification: Notification) {
        saveExpandedFrame()
    }

    func windowDidResize(_ notification: Notification) {
        saveExpandedFrame()
    }

    private func saveExpandedFrame() {
        guard !isCollapsed, panel != nil else {
            return
        }

        UserDefaults.standard.set(NSStringFromRect(panel.frame), forKey: frameDefaultsKey)
    }

    private func loadSavedFrame() -> NSRect {
        if
            let saved = UserDefaults.standard.string(forKey: frameDefaultsKey),
            !saved.isEmpty
        {
            let frame = NSRectFromString(saved)
            if frame.width >= minimumPanelSize.width && frame.height >= minimumPanelSize.height {
                return frame
            }
        }

        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1280, height: 800)
        return NSRect(
            x: screenFrame.maxX - defaultPanelSize.width - 24,
            y: screenFrame.maxY - defaultPanelSize.height - 44,
            width: defaultPanelSize.width,
            height: defaultPanelSize.height
        )
    }

    private static let hudHTML = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
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
        html, body {
          width: 100%;
          min-height: 100%;
          margin: 0;
          background:
            radial-gradient(circle at 50% -20%, rgba(40,215,255,.14), transparent 26rem),
            linear-gradient(180deg, #080a0f 0%, #0d1119 60%, #080a0f 100%);
          color: var(--text);
          font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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
          background-size: 42px 42px;
          mask-image: linear-gradient(180deg, rgba(0,0,0,.86), transparent);
        }
        #app {
          position: relative;
          z-index: 1;
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
        }
        .empty {
          min-height: calc(100vh - 24px);
          display: grid;
          place-items: center;
          color: rgba(230, 240, 255, .72);
          font-size: 13px;
          animation: emptyPulse 1.8s ease-in-out infinite;
        }
        .run {
          border: 1px solid var(--line);
          border-radius: 8px;
          background: linear-gradient(180deg, rgba(21,29,43,.92), rgba(11,15,23,.96));
          overflow: hidden;
        }
        .run.live {
          border-color: rgba(40,215,255,.42);
          box-shadow: 0 0 34px rgba(40,215,255,.10);
        }
        .run.finished {
          opacity: .72;
        }
        .run.died {
          border-color: rgba(255,84,104,.58);
          background: linear-gradient(180deg, rgba(46,18,25,.92), rgba(14,10,14,.96));
        }
        .run-head {
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          gap: 8px;
          align-items: center;
          padding: 10px 10px 8px;
          border-bottom: 1px solid rgba(255,255,255,.08);
        }
        .dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--gray);
          box-shadow: 0 0 16px rgba(119,129,149,.7);
        }
        .dot.live {
          background: var(--cyan);
          animation: dotPulse 1.35s infinite;
        }
        .dot.finished { background: var(--green); }
        .dot.died { background: var(--red); box-shadow: 0 0 18px rgba(255,84,104,.78); }
        .run-main {
          min-width: 0;
          display: flex;
          align-items: center;
          gap: 7px;
        }
        .run-name {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 13px;
          font-weight: 800;
          letter-spacing: 0;
        }
        .identity {
          flex: 0 0 auto;
          max-width: 112px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          border-radius: 999px;
          padding: 3px 7px;
          background: color-mix(in srgb, var(--identity) 22%, transparent);
          border: 1px solid color-mix(in srgb, var(--identity) 70%, transparent);
          color: #ecf8ff;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 10px;
          font-weight: 800;
        }
        .run-meta {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 2px;
          color: #cbd6e8;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 11px;
          line-height: 1.18;
        }
        .final {
          color: var(--muted);
        }
        .tasks {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(106px, 1fr));
          gap: 7px;
          padding: 9px;
        }
        .task {
          min-width: 0;
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 4px 6px;
          align-items: center;
          border: 1px solid rgba(255,255,255,.08);
          border-left: 3px solid var(--gray);
          border-radius: 7px;
          background: rgba(255,255,255,.035);
          padding: 7px;
        }
        .task.running, .task.retrying { border-left-color: var(--cyan); }
        .task.verifying { border-left-color: var(--amber); }
        .task.pass { border-left-color: var(--green); }
        .task.fail { border-left-color: var(--red); }
        .task-key {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
          font-weight: 800;
        }
        .task-status {
          border-radius: 999px;
          padding: 3px 5px;
          background: var(--gray);
          color: #080a0f;
          font-size: 9px;
          font-weight: 900;
          text-transform: uppercase;
        }
        .task.running .task-status, .task.retrying .task-status { background: var(--cyan); }
        .task.verifying .task-status { background: var(--amber); }
        .task.pass .task-status { background: var(--green); }
        .task.fail .task-status { background: var(--red); }
        .task-elapsed, .children {
          color: var(--muted);
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 10px;
        }
        .children {
          text-align: right;
          color: #b9f3ff;
          font-weight: 800;
        }
        @keyframes dotPulse {
          0% { box-shadow: 0 0 0 0 rgba(40,215,255,.62), 0 0 24px rgba(40,215,255,.86); }
          70% { box-shadow: 0 0 0 12px rgba(40,215,255,0), 0 0 24px rgba(40,215,255,.86); }
          100% { box-shadow: 0 0 0 0 rgba(40,215,255,0), 0 0 24px rgba(40,215,255,.86); }
        }
        @keyframes emptyPulse {
          0%, 100% { opacity: .38; transform: scale(.985); }
          50% { opacity: .90; transform: scale(1); }
        }
      </style>
    </head>
    <body>
      <main id="app"><div class="empty">no swarms running</div></main>
      <script>
        const app = document.getElementById("app");
        const htmlEscapes = {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"};

        function escapeHTML(value) {
          return String(value ?? "").replace(/[&<>"']/g, char => htmlEscapes[char]);
        }

        function identityColor(name) {
          let hash = 2166136261;
          const text = String(name || "unknown");
          for (let i = 0; i < text.length; i++) {
            hash ^= text.charCodeAt(i);
            hash = Math.imul(hash, 16777619);
          }
          const hue = (hash >>> 0) % 360;
          return `hsl(${hue} 78% 58%)`;
        }

        function fmtElapsed(seconds) {
          seconds = Math.max(0, Math.floor(seconds || 0));
          const h = Math.floor(seconds / 3600);
          const m = Math.floor((seconds % 3600) / 60);
          const s = seconds % 60;
          if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
          return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
        }

        function renderTask(task) {
          const children = Number(task.children || 0);
          return `
            <div class="task ${escapeHTML(task.status || "queued")}">
              <div class="task-key" title="${escapeHTML(task.key)}">${escapeHTML(task.key)}</div>
              <div class="task-status">${escapeHTML(task.status || "queued")}</div>
              <div class="task-elapsed">${fmtElapsed(task.elapsed_s)}</div>
              <div class="children">${children > 0 ? `⤷${children}` : ""}</div>
            </div>
          `;
        }

        function renderRun(run) {
          const identity = run.identity || "unknown";
          const pass = Number(run.pass || 0);
          const fail = Number(run.fail || 0);
          const final = run.state === "finished" ? `<span class="final">✓${pass} ✗${fail}</span>` : "";
          const tasks = (run.tasks || []).map(renderTask).join("");
          return `
            <section class="run ${escapeHTML(run.state)}">
              <header class="run-head">
                <span class="dot ${escapeHTML(run.state)}"></span>
                <div class="run-main">
                  <div class="run-name" title="${escapeHTML(run.run_name)}">${escapeHTML(run.run_name || "swarm")}</div>
                  <span class="identity" style="--identity:${identityColor(identity)}" title="${escapeHTML(identity)}">${escapeHTML(identity)}</span>
                </div>
                <div class="run-meta">
                  <span>${fmtElapsed(run.elapsed_s)}</span>
                  <span>${Number(run.tokens || 0).toLocaleString()} tok</span>
                  ${final}
                </div>
              </header>
              <div class="tasks">${tasks || `<div class="task"><div class="task-key">no tasks</div><div class="task-status">idle</div><div class="task-elapsed">00:00</div><div></div></div>`}</div>
            </section>
          `;
        }

        function update(payload) {
          const runs = payload?.runs || [];
          if (runs.length === 0) {
            app.innerHTML = `<div class="empty">no swarms running</div>`;
            return;
          }
          app.innerHTML = runs.map(renderRun).join("");
        }
      </script>
    </body>
    </html>
    """
}

private let isoWithFractionalSeconds: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

private let isoWithoutFractionalSeconds: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
}()

private func parseISODate(_ value: String?) -> Date? {
    guard let value, !value.isEmpty else {
        return nil
    }
    return isoWithFractionalSeconds.date(from: value) ?? isoWithoutFractionalSeconds.date(from: value)
}

private func stringValue(_ value: Any?) -> String? {
    if let string = value as? String {
        return string
    }
    if let number = value as? NSNumber {
        return number.stringValue
    }
    return nil
}

private func intValue(_ value: Any?) -> Int? {
    if let int = value as? Int {
        return int
    }
    if let number = value as? NSNumber {
        return number.intValue
    }
    if let string = value as? String {
        return Int(string)
    }
    return nil
}

private func doubleValue(_ value: Any?) -> Double? {
    if let double = value as? Double {
        return double
    }
    if let number = value as? NSNumber {
        return number.doubleValue
    }
    if let string = value as? String {
        return Double(string)
    }
    return nil
}

private func boolValue(_ value: Any?) -> Bool? {
    if let bool = value as? Bool {
        return bool
    }
    if let number = value as? NSNumber {
        return number.boolValue
    }
    if let string = value as? String {
        switch string.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "true", "1", "yes":
            return true
        case "false", "0", "no":
            return false
        default:
            return nil
        }
    }
    return nil
}

let app = NSApplication.shared
private let delegate = AppDelegate()
app.delegate = delegate
app.run()
