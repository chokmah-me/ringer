#Requires -Version 7.0
<#
.SYNOPSIS
  Build an evidence pack of ongoing work for Ringer model-mix routing.

.DESCRIPTION
  Reads session-recall-cc, 00Dev git activity, ringer runs/scoreboard,
  home-silo memory (model pool), and ringer config engines.
  Writes signals.json + signals.md (and optionally scoreboard into the pack).

.PARAMETER Days
  Lookback window for session-recall and "recent" git. Default 14.

.PARAMETER OutDir
  Directory for signals.json / signals.md. Default: ~/.ringer/model-mix/_work

.PARAMETER RingerHome
  Path to ringer repo (contains ringer.py). Default: Documents/00Dev/ringer
#>
[CmdletBinding()]
param(
    [int] $Days = 14,
    [string] $OutDir = "",
    [string] $RingerHome = "",
    [string] $DevRoot = ""
)

$ErrorActionPreference = 'Continue'
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
if (-not $OutDir) {
    $OutDir = Join-Path $env:USERPROFILE '.ringer\model-mix\_work'
}
if (-not $RingerHome) {
    $RingerHome = Join-Path $env:USERPROFILE 'Documents\00Dev\ringer'
}
if (-not $DevRoot) {
    $DevRoot = Join-Path $env:USERPROFILE 'Documents\00Dev'
}
$MemoryRoot = Join-Path $env:USERPROFILE '.claude\projects\C--Users-Elke-Shayna\memory'
$ConfigToml = Join-Path $env:USERPROFILE '.config\ringer\config.toml'
$RunsJsonl = Join-Path $env:USERPROFILE '.ringer\runs.jsonl'

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Get-TaskTypesForName([string] $name) {
    $n = $name.ToLowerInvariant()
    if ($n -match 'pipl|arch') { return @('code-feature', 'code-fix', 'test-hardening') }
    if ($n -eq 'ringer') { return @('code-feature', 'probe', 'docs', 'code-review') }
    if ($n -match 'chokmah|continuity|milcom|paper|research|computability|schmitt|willow|loop-engineering|attrition') {
        return @('research', 'docs', 'adversarial-review')
    }
    if ($n -match 'grandprix|aegis|racer') { return @('code-feature', 'code-fix') }
    if ($n -match 'munder|dyb|site|hashline') { return @('docs', 'site-build', 'copywriting') }
    if ($n -match 'eml|ice40|fiber|dwell') { return @('code-feature', 'docs') }
    return @('code-feature', 'docs')
}

function Merge-Project {
    param(
        $Map,
        [string] $Name,
        [string] $Path = '',
        [string] $Signal,
        [string[]] $TaskTypes = @()
    )
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $key = $Name.Trim()
    if (-not $Map.ContainsKey($key)) {
        $Map[$key] = @{
            name               = $key
            path               = $Path
            signals            = [System.Collections.Generic.List[string]]::new()
            likely_task_types  = [System.Collections.Generic.List[string]]::new()
            session_summaries  = [System.Collections.Generic.List[string]]::new()
            last_git           = $null
        }
    }
    $p = $Map[$key]
    if ($Path -and [string]::IsNullOrWhiteSpace([string]$p.path)) { $p.path = $Path }
    if ($Signal -and -not $p.signals.Contains($Signal)) { $p.signals.Add($Signal) }
    foreach ($t in $TaskTypes) {
        if ($t -and -not $p.likely_task_types.Contains($t)) { $p.likely_task_types.Add($t) }
    }
}

$projects = @{}
$sessionsRaw = $null
$filesRaw = $null
$searches = @{}
$engines = @()
$scoreboardText = ''
$exploreText = ''
$memoryExcerpts = [ordered]@{}
$errors = [System.Collections.Generic.List[string]]::new()

# --- session-recall list ---
try {
    $out = & session-recall-cc list --days $Days --limit 40 --json 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $out.Trim().StartsWith('{')) {
        $sessionsRaw = $out | ConvertFrom-Json
        foreach ($s in @($sessionsRaw.sessions)) {
            $repo = if ($s.repository) { ($s.repository -split '/')[-1] } else { '' }
            $cwd = [string]$s.cwd
            $name = if ($repo) { $repo } elseif ($cwd) { Split-Path $cwd -Leaf } else { 'unknown' }
            if ($name -in @('Elke Shayna', 'Users', 'HOME')) { $name = 'home-workspace' }
            $types = Get-TaskTypesForName $name
            Merge-Project -Map $projects -Name $name -Path $cwd -Signal 'session-recall' -TaskTypes $types
            if ($s.summary) {
                $summary = [string]$s.summary
                if ($summary.Length -gt 120) { $summary = $summary.Substring(0, 117) + '...' }
                if ($projects[$name].session_summaries.Count -lt 5) {
                    $projects[$name].session_summaries.Add($summary)
                }
            }
        }
    } else {
        $errors.Add("session-recall list: $out")
    }
} catch {
    $errors.Add("session-recall list exception: $_")
}

# --- session-recall files ---
try {
    $out = & session-recall-cc files --days $Days --limit 40 --json 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $out.Trim().StartsWith('{')) {
        $filesRaw = $out | ConvertFrom-Json
        foreach ($f in @($filesRaw.files)) {
            $fp = [string]$f.file_path
            if ($fp -match 'Documents\\00Dev\\([^\\]+)') {
                $name = $Matches[1]
                Merge-Project -Map $projects -Name $name -Path (Join-Path $DevRoot $name) -Signal 'session-files' -TaskTypes (Get-TaskTypesForName $name)
            }
        }
    }
} catch {
    $errors.Add("session-recall files exception: $_")
}

# --- simple FTS searches (no * or complex OR) ---
foreach ($q in @('PIPL', 'ringer', 'chokmah', 'GrandPrix', 'Jan', 'AIGrandPrix')) {
    try {
        $out = & session-recall-cc search $q --days $Days --limit 8 --json 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0 -and $out.Trim().StartsWith('{')) {
            $js = $out | ConvertFrom-Json
            $searches[$q] = @($js.results | ForEach-Object {
                [ordered]@{
                    repository = $_.repository
                    snippet    = if ($_.user_msg) {
                        $m = [string]$_.user_msg
                        if ($m.Length -gt 160) { $m.Substring(0, 157) + '...' } else { $m }
                    } else { $_.snippet }
                    last_seen  = $_.last_seen
                }
            })
            foreach ($r in @($js.results)) {
                $repo = [string]$r.repository
                if ($repo -match '00Dev/([^/]+)') {
                    $name = $Matches[1]
                    Merge-Project -Map $projects -Name $name -Path (Join-Path $DevRoot $name) -Signal "search:$q" -TaskTypes (Get-TaskTypesForName $name)
                }
            }
        } else {
            $searches[$q] = @()
        }
    } catch {
        $searches[$q] = @()
        $errors.Add("search $q : $_")
    }
}

# --- git repos under 00Dev ---
$gitRepos = @()
if (Test-Path $DevRoot) {
    Get-ChildItem $DevRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $gitDir = Join-Path $_.FullName '.git'
        if (-not (Test-Path $gitDir)) { return }
        Push-Location $_.FullName
        try {
            $last = & git log -1 --format='%ci|%s' 2>$null
            $when = $null
            $subj = $null
            if ($last) {
                $parts = $last -split '\|', 2
                $when = $parts[0]
                $subj = if ($parts.Count -gt 1) { $parts[1] } else { '' }
            }
            $entry = [ordered]@{
                name    = $_.Name
                path    = $_.FullName
                last_ci = $when
                subject = $subj
            }
            $gitRepos += $entry
            $include = $true
            if ($when) {
                try {
                    $dt = [datetime]::Parse($when)
                    if ($dt -lt (Get-Date).AddDays(-[Math]::Max($Days, 30))) {
                        # still include top active; mark signal only if recent enough
                        $include = $dt -ge (Get-Date).AddDays(-45)
                    }
                } catch { }
            }
            if ($include -or ($_.Name -match 'ringer|PIPL|chokmah|AIGrandPrix|continuity')) {
                Merge-Project -Map $projects -Name $_.Name -Path $_.FullName -Signal 'git' -TaskTypes (Get-TaskTypesForName $_.Name)
                if ($projects.ContainsKey($_.Name)) {
                    $projects[$_.Name]['last_git'] = @{ when = $when; subject = $subj }
                }
            }
        } finally {
            Pop-Location
        }
    }
}

# --- engines from config.toml ---
if (Test-Path $ConfigToml) {
    Select-String -Path $ConfigToml -Pattern '^\[engines\.([^\]]+)\]' | ForEach-Object {
        $engines += $_.Matches[0].Groups[1].Value
    }
}

# --- memory excerpts ---
foreach ($mem in @('model-pool-current.md', 'user-work-fingerprint.md', 'model-pool-current.md')) {
    $mp = Join-Path $MemoryRoot $mem
    if (Test-Path $mp) {
        $txt = Get-Content $mp -Raw -ErrorAction SilentlyContinue
        if ($txt.Length -gt 2500) { $txt = $txt.Substring(0, 2500) + "`n...[truncated]" }
        $memoryExcerpts[$mem] = $txt
    }
}
# unique keys only once
$poolPath = Join-Path $MemoryRoot 'model-pool-current.md'

# --- ringer.py models ---
if (Test-Path (Join-Path $RingerHome 'ringer.py')) {
    try {
        Push-Location $RingerHome
        $scoreboardText = & python ringer.py models 2>&1 | Out-String
        $exploreText = & python ringer.py models --explore 2>&1 | Out-String
    } catch {
        $errors.Add("ringer models: $_")
    } finally {
        Pop-Location
    }
} else {
    $errors.Add("ringer.py not found at $RingerHome")
}

# --- recent runs.jsonl sample ---
$recentRuns = @()
if (Test-Path $RunsJsonl) {
    Get-Content $RunsJsonl -Tail 30 -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $row = $_ | ConvertFrom-Json
            $recentRuns += [ordered]@{
                logged_at  = $row.logged_at
                task_type  = $row.task_type
                model      = $row.model
                verdict    = $row.verdict
                run_id     = $row.run_id
                engine     = $row.worker_engine
            }
            if ($row.task_type) {
                # attach task type to any project that already exists; also track global
            }
        } catch { }
    }
}

$taskTypesActive = [System.Collections.Generic.HashSet[string]]::new()
foreach ($k in $projects.Keys) {
    foreach ($t in $projects[$k].likely_task_types) { [void]$taskTypesActive.Add($t) }
}
foreach ($r in $recentRuns) {
    if ($r.task_type) { [void]$taskTypesActive.Add([string]$r.task_type) }
}

# materialize projects list
$projectList = @()
foreach ($k in $projects.Keys) {
    $p = $projects[$k]
    $projectList += [ordered]@{
        name              = $p.name
        path              = $p.path
        signals           = @($p.signals)
        likely_task_types = @($p.likely_task_types)
        session_summaries = @($p.session_summaries)
        last_git          = $p.last_git
    }
}

$pack = [ordered]@{
    generated_at       = (Get-Date).ToString('o')
    days               = $Days
    ringer_home        = $RingerHome
    dev_root           = $DevRoot
    engines            = $engines
    model_pool_path    = $poolPath
    projects           = $projectList
    task_types_active  = @($taskTypesActive)
    session_searches   = $searches
    recent_runs_sample = $recentRuns
    scoreboard_text    = $scoreboardText
    explore_text       = $exploreText
    memory_excerpts    = $memoryExcerpts
    errors             = @($errors)
}

$jsonPath = Join-Path $OutDir "signals-$stamp.json"
$mdPath = Join-Path $OutDir "signals-$stamp.md"
$latestJson = Join-Path $OutDir 'signals-latest.json'
$latestMd = Join-Path $OutDir 'signals-latest.md'

$pack | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding utf8
Copy-Item $jsonPath $latestJson -Force

# Markdown human pack
$md = [System.Text.StringBuilder]::new()
[void]$md.AppendLine("# Work signals ($stamp)")
[void]$md.AppendLine()
[void]$md.AppendLine("Generated: $($pack.generated_at)")
[void]$md.AppendLine("Lookback days: $Days")
[void]$md.AppendLine("Engines: $($engines -join ', ')")
[void]$md.AppendLine()
[void]$md.AppendLine('## Projects')
foreach ($p in $projectList) {
    [void]$md.AppendLine("### $($p.name)")
    [void]$md.AppendLine("- path: $($p.path)")
    [void]$md.AppendLine("- signals: $($p.signals -join ', ')")
    [void]$md.AppendLine("- likely task_types: $($p.likely_task_types -join ', ')")
    if ($p.last_git) {
        [void]$md.AppendLine("- last git: $($p.last_git.when) — $($p.last_git.subject)")
    }
    if ($p.session_summaries.Count) {
        [void]$md.AppendLine('- recent session summaries:')
        foreach ($s in $p.session_summaries) { [void]$md.AppendLine("  - $s") }
    }
    [void]$md.AppendLine()
}
[void]$md.AppendLine('## Active task_types')
[void]$md.AppendLine(($taskTypesActive -join ', '))
[void]$md.AppendLine()
[void]$md.AppendLine('## Model pool (home memory)')
if ($memoryExcerpts.Contains('model-pool-current.md')) {
    [void]$md.AppendLine('```')
    [void]$md.AppendLine($memoryExcerpts['model-pool-current.md'])
    [void]$md.AppendLine('```')
}
[void]$md.AppendLine()
[void]$md.AppendLine('## Ringer scoreboard (`ringer.py models`)')
[void]$md.AppendLine('```')
[void]$md.AppendLine($scoreboardText)
[void]$md.AppendLine('```')
[void]$md.AppendLine()
[void]$md.AppendLine('## Explore candidates')
[void]$md.AppendLine('```')
[void]$md.AppendLine($exploreText)
[void]$md.AppendLine('```')
if ($errors.Count) {
    [void]$md.AppendLine()
    [void]$md.AppendLine('## Collector errors')
    foreach ($e in $errors) { [void]$md.AppendLine("- $e") }
}

$md.ToString() | Set-Content -Path $mdPath -Encoding utf8
Copy-Item $mdPath $latestMd -Force

Write-Host "Wrote $jsonPath"
Write-Host "Wrote $mdPath"
Write-Host "Projects: $($projectList.Count)"
# Return paths for callers
[pscustomobject]@{
    JsonPath     = $jsonPath
    MdPath       = $mdPath
    LatestJson   = $latestJson
    LatestMd     = $latestMd
    ProjectCount = $projectList.Count
}
