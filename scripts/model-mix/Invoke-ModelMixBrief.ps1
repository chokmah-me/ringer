#Requires -Version 7.0
<#
.SYNOPSIS
  Collect work signals + local scoreboard, then LLM-write a Ringer model-mix brief.

.DESCRIPTION
  Full pipeline for the twice-weekly ModelMixRefresh task.
  Evidence is pre-injected; Claude/Grok run tool-free (-p / headless) so the job does not hang on permissions.
  Does NOT run ringer.py run (no swarms).

.PARAMETER SkipLlm
  Only collect signals (no Claude/Grok).

.PARAMETER Provider
  claude | grok | auto (default auto: try grok then claude — Grok first because
  ANTHROPIC_API_KEY often breaks headless claude -p on this machine)
#>
[CmdletBinding()]
param(
    [switch] $SkipLlm,
    [ValidateSet('auto', 'claude', 'grok')]
    [string] $Provider = 'auto',
    [string] $RingerHome = '',
    [int] $Days = 14
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
if (-not $RingerHome) {
    $RingerHome = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
}

$OutRoot = Join-Path $env:USERPROFILE '.ringer\model-mix'
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$RunDir = Join-Path $OutRoot "runs\$stamp"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
$LogPath = Join-Path $RunDir 'run.log'

function Write-Log([string] $msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'o'), $msg
    Add-Content -Path $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

Write-Log "START ModelMixBrief runDir=$RunDir ringerHome=$RingerHome"

try {
    # 1) Collect
    $collectScript = Join-Path $ScriptDir 'Collect-WorkSignals.ps1'
    $workDir = Join-Path $OutRoot '_work'
    Write-Log "Collecting signals..."
    $collect = & $collectScript -Days $Days -OutDir $workDir -RingerHome $RingerHome
    $signalsMd = $collect.LatestMd
    $signalsJson = $collect.LatestJson
    Copy-Item $signalsMd (Join-Path $RunDir 'signals.md') -Force
    Copy-Item $signalsJson (Join-Path $RunDir 'signals.json') -Force
    Write-Log "Signals projects=$($collect.ProjectCount) md=$signalsMd"

    if ($collect.ProjectCount -lt 1) {
        throw "No projects discovered — aborting brief"
    }

    if ($SkipLlm) {
        Write-Log "SkipLlm set — done after collect"
        exit 0
    }

    $promptFile = Join-Path $ScriptDir 'prompts\model-mix-brief.md'
    $systemPrompt = Get-Content $promptFile -Raw -Encoding utf8
    # Keep argv short (Windows ~8k limit): evidence stays on disk; LLM reads via Read tool.
    $signalsInRun = Join-Path $RunDir 'signals.md'
    $userPrompt = @"
Read the evidence file at:
  $signalsInRun

Use only that file plus the system rules. Produce BRIEF and STANDING_MIX_JSON blocks now. Do not run ringer swarms. Do not edit any other files.
"@
    $sysFile = Join-Path $RunDir 'system-prompt.txt'
    $userFile = Join-Path $RunDir 'user-prompt.txt'
    Set-Content -Path $sysFile -Value $systemPrompt -Encoding utf8
    Set-Content -Path $userFile -Value $userPrompt -Encoding utf8

    $rawOutPath = Join-Path $RunDir 'llm-raw.txt'
    $llmOk = $false
    $providerUsed = $null

    function New-HeuristicBrief {
        param([string] $SignalsJsonPath)
        $pack = Get-Content $SignalsJsonPath -Raw | ConvertFrom-Json
        # Parse simple winners from scoreboard text lines: task_type, model, first_try near end
        # Prefer known good defaults constrained to pool + engines.
        $engines = @($pack.engines)
        $hasOpencode = $engines -contains 'opencode'
        $hasGrok = $engines -contains 'grok'
        $hasCodex = $engines -contains 'codex'

        # Defaults grounded in local scoreboard snapshot (user machine, 2026-07):
        # code-feature: Grok 4.5 / Composer strong; code-fix: Grok 4.5 + GLM; code-review: Composer; probe: many OK
        $global = [ordered]@{
            'code-feature' = @{ engine = $(if ($hasOpencode) { 'opencode' } elseif ($hasGrok) { 'grok' } else { 'codex' }); model = $(if ($hasOpencode) { 'openrouter/x-ai/grok-4.5' } else { $null }) }
            'code-fix'     = @{ engine = $(if ($hasOpencode) { 'opencode' } else { 'codex' }); model = $(if ($hasOpencode) { 'openrouter/x-ai/grok-4.5' } else { $null }) }
            'code-review'  = @{ engine = $(if ($hasGrok) { 'grok' } elseif ($hasOpencode) { 'opencode' } else { 'codex' }); model = $(if ($hasGrok) { $null } elseif ($hasOpencode) { 'openrouter/z-ai/glm-5.2' } else { $null }) }
            'research'     = @{ engine = $(if ($hasOpencode) { 'opencode' } else { 'codex' }); model = $(if ($hasOpencode) { 'openrouter/anthropic/claude-sonnet-5' } else { $null }) }
            'docs'         = @{ engine = $(if ($hasOpencode) { 'opencode' } else { 'codex' }); model = $(if ($hasOpencode) { 'openrouter/z-ai/glm-5.2' } else { $null }) }
            'probe'        = @{ engine = $(if ($hasOpencode) { 'opencode' } else { 'codex' }); model = $(if ($hasOpencode) { 'deepseek/deepseek-v4-pro' } else { $null }) }
        }
        # Pool-aware override: model-pool lists GLM, DeepSeek flash/pro, composer, fable, opus, sonnet
        # Map composer to grok engine when available
        if ($hasGrok) {
            $global['code-review'] = @{ engine = 'grok'; model = $null }
        }

        $projectsObj = [ordered]@{}
        $briefLines = [System.Collections.Generic.List[string]]::new()
        $briefLines.Add("# Model mix brief — $(Get-Date -Format 'yyyy-MM-dd') (scoreboard-heuristic)")
        $briefLines.Add('')
        $briefLines.Add('> LLM providers unavailable; recommendations derived from local `ringer.py models` history + model-pool memory. Re-run when Claude/Grok auth works for a full brief.')
        $briefLines.Add('')
        $briefLines.Add('## Global defaults')
        foreach ($k in $global.Keys) {
            $eng = $global[$k].engine
            $mod = $global[$k].model
            $briefLines.Add("- **${k}**: engine=$eng model=$mod")
        }
        $briefLines.Add('')
        $briefLines.Add('## Per-project')
        foreach ($p in @($pack.projects)) {
            $name = [string]$p.name
            $types = @($p.likely_task_types)
            $primary = if ($types -contains 'code-feature') { 'code-feature' }
                elseif ($types -contains 'code-fix') { 'code-fix' }
                elseif ($types -contains 'research') { 'research' }
                elseif ($types -contains 'docs') { 'docs' }
                else { 'probe' }
            $def = $global[$primary]
            $by = [ordered]@{}
            foreach ($t in $types) {
                if ($global.Contains($t)) {
                    $by[$t] = @{ engine = $global[$t].engine; model = $global[$t].model; rationale = 'scoreboard-heuristic default' }
                }
            }
            $projectsObj[$name] = [ordered]@{
                path              = $p.path
                default_engine    = $def.engine
                default_model     = $def.model
                by_task_type      = $by
                explore_candidate = @{ engine = 'opencode'; model = 'deepseek/deepseek-v4-pro'; task_type = 'probe' }
                notes             = "signals: $($p.signals -join ', '); heuristic primary=$primary"
            }
            $briefLines.Add("### $name")
            $briefLines.Add("- default: engine=$($def.engine) model=$($def.model) (primary task_type=$primary)")
            $briefLines.Add("- task_types: $($types -join ', ')")
            $briefLines.Add("- path: $($p.path)")
            $briefLines.Add('')
        }
        $standing = [ordered]@{
            updated             = (Get-Date).ToString('o')
            source              = 'scoreboard-heuristic'
            pool_constraint     = @('GLM 5.2', 'DeepSeek V4 Flash', 'DeepSeek V4 Pro', 'grok-composer-2.5-fast', 'claude-fable-5', 'claude-opus-8', 'claude-sonnet-5')
            engines_available   = $engines
            projects            = $projectsObj
            global_defaults     = $global
        }
        $json = $standing | ConvertTo-Json -Depth 10
        $md = $briefLines -join "`n"
        $nl = [Environment]::NewLine
        return ('```BRIEF' + $nl + $md + $nl + '```' + $nl + $nl + '```STANDING_MIX_JSON' + $nl + $json + $nl + '```')
    }

    function Invoke-ClaudeBrief {
        $claude = Get-Command claude -ErrorAction SilentlyContinue
        if (-not $claude) { throw 'claude not on PATH' }
        Write-Log 'Invoking claude -p (Read-only tools, evidence on disk)...'
        $sysBody = Get-Content $sysFile -Raw
        $userBody = Get-Content $userFile -Raw
        $stderrFile = Join-Path $RunDir 'llm-stderr.txt'
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            # Do NOT use --bare (skips OAuth). Allow only Read so the job can load signals.md.
            $output = & claude -p `
                --allowedTools Read `
                --add-dir $RunDir `
                --system-prompt $sysBody `
                $userBody 2> $stderrFile
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($null -eq $output) { $output = '' }
        $text = if ($output -is [array]) { $output -join "`n" } else { [string]$output }
        Set-Content -Path $rawOutPath -Value $text -Encoding utf8
        if ([string]::IsNullOrWhiteSpace($text)) {
            throw "claude returned empty output (exit $code); see llm-stderr.txt"
        }
        if ($text -match 'Invalid API key|authentication|not logged in|Unauthorized') {
            throw "claude auth/API error: $text"
        }
        if ($text.Length -lt 200 -and $text -notmatch 'STANDING_MIX_JSON|BRIEF') {
            throw "claude output too short / not a brief: $text"
        }
        return $text
    }

    function Invoke-GrokBrief {
        $grok = Get-Command grok -ErrorAction SilentlyContinue
        if (-not $grok) { throw 'grok not on PATH' }
        Write-Log 'Invoking grok headless (--prompt-file; evidence inlined)...'
        # Inline evidence so the job is tool-free. Must use --prompt-file: a 20k+
        # argv hits the Windows CreateProcess command-line limit (~32k) and fails silently.
        $evidence = Get-Content $signalsInRun -Raw
        $combined = @"
$(Get-Content $sysFile -Raw)

---

$(Get-Content $userFile -Raw)

--- EVIDENCE FILE CONTENTS ---
$evidence
--- END ---

Produce the BRIEF and STANDING_MIX_JSON fenced blocks now. No tool use required — all evidence is above. Do not run ringer swarms.
"@
        $combinedPath = Join-Path $RunDir 'grok-combined.txt'
        Set-Content -Path $combinedPath -Value $combined -Encoding utf8
        $stderrFile = Join-Path $RunDir 'llm-stderr.txt'
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            # Headless single-shot: prompt from file, auto-approve, few turns, no tools.
            $output = & grok `
                --prompt-file $combinedPath `
                --always-approve `
                --max-turns 4 `
                --tools '' `
                --output-format plain `
                --cwd $RingerHome `
                2> $stderrFile
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($null -eq $output) { $output = '' }
        $text = if ($output -is [array]) { $output -join "`n" } else { [string]$output }
        Set-Content -Path $rawOutPath -Value $text -Encoding utf8
        if ([string]::IsNullOrWhiteSpace($text)) {
            $errTail = if (Test-Path $stderrFile) { (Get-Content $stderrFile -Raw) } else { '' }
            throw "grok returned empty output (exit $code); stderr: $errTail"
        }
        if ($text -match 'Invalid API key|authentication failed|not logged in|Unauthorized|401') {
            throw "grok auth/API error: $text"
        }
        if ($text.Length -lt 200 -and $text -notmatch 'STANDING_MIX_JSON|BRIEF') {
            throw "grok output too short / not a brief: $text"
        }
        return $text
    }

    $raw = $null
    $tryOrder = switch ($Provider) {
        'claude' { @('claude') }
        'grok' { @('grok') }
        default { @('grok', 'claude') }
    }
    foreach ($p in $tryOrder) {
        try {
            if ($p -eq 'claude') { $raw = Invoke-ClaudeBrief; $providerUsed = 'claude'; $llmOk = $true; break }
            if ($p -eq 'grok') { $raw = Invoke-GrokBrief; $providerUsed = 'grok'; $llmOk = $true; break }
        } catch {
            Write-Log "Provider $p failed: $_"
        }
    }
    if (-not $llmOk) {
        Write-Log 'All LLM providers failed — building scoreboard-heuristic brief (no LLM)'
        $providerUsed = 'scoreboard-heuristic'
        $raw = New-HeuristicBrief -SignalsJsonPath (Join-Path $RunDir 'signals.json')
        $llmOk = $true
    }
    Write-Log "Brief ok provider=$providerUsed chars=$($raw.Length)"

    # 2) Extract BRIEF and STANDING_MIX_JSON
    $briefPath = Join-Path $RunDir 'brief.md'
    $jsonPath = Join-Path $RunDir 'standing-mix.json'

    $brief = $null
    $jsonText = $null
    if ($raw -match '(?s)```BRIEF\s*(.*?)\s*```') {
        $brief = $Matches[1].Trim()
    } elseif ($raw -match '(?s)```markdown\s*(.*?)\s*```') {
        $brief = $Matches[1].Trim()
    } else {
        $brief = $raw.Trim()
    }
    if ($raw -match '(?s)```STANDING_MIX_JSON\s*(.*?)\s*```') {
        $jsonText = $Matches[1].Trim()
    } elseif ($raw -match '(?s)```json\s*(\{.*?\})\s*```') {
        $jsonText = $Matches[1].Trim()
    }

    Set-Content -Path $briefPath -Value $brief -Encoding utf8

    $standing = $null
    if ($jsonText) {
        try {
            $standing = $jsonText | ConvertFrom-Json
            $jsonText | Set-Content -Path $jsonPath -Encoding utf8
        } catch {
            Write-Log "JSON parse failed, wrapping raw: $_"
            $standing = [ordered]@{
                updated            = (Get-Date).ToString('o')
                source             = 'scheduled-model-mix-brief'
                parse_error        = "$_"
                raw_json_text      = $jsonText
                provider           = $providerUsed
            }
            ($standing | ConvertTo-Json -Depth 8) | Set-Content -Path $jsonPath -Encoding utf8
        }
    } else {
        Write-Log "No STANDING_MIX_JSON fence found — writing stub"
        $standing = [ordered]@{
            updated     = (Get-Date).ToString('o')
            source      = 'scheduled-model-mix-brief'
            parse_error = 'missing STANDING_MIX_JSON block'
            provider    = $providerUsed
            projects    = @{}
        }
        ($standing | ConvertTo-Json -Depth 6) | Set-Content -Path $jsonPath -Encoding utf8
    }

    # Standing locks (enforced after LLM parse — prompt may be ignored)
    # probe → opencode / deepseek/deepseek-v4-pro (user lock)
    if ($null -ne $standing -and -not $standing.parse_error) {
        $probeLock = [ordered]@{
            engine = 'opencode'
            model  = 'deepseek/deepseek-v4-pro'
        }
        $probeRationale = 'user lock: DeepSeek for probe'
        try {
            if (-not $standing.global_defaults) {
                $standing | Add-Member -NotePropertyName global_defaults -NotePropertyValue ([pscustomobject]@{}) -Force
            }
            $standing.global_defaults | Add-Member -NotePropertyName probe -NotePropertyValue ([pscustomobject]$probeLock) -Force
            if ($standing.projects) {
                foreach ($pn in @($standing.projects.PSObject.Properties.Name)) {
                    $proj = $standing.projects.$pn
                    if ($proj.by_task_type -and ($proj.by_task_type.PSObject.Properties.Name -contains 'probe')) {
                        $proj.by_task_type | Add-Member -NotePropertyName probe -NotePropertyValue ([pscustomobject]@{
                                engine    = $probeLock.engine
                                model     = $probeLock.model
                                rationale = $probeRationale
                            }) -Force
                    }
                }
            }
            $standing | Add-Member -NotePropertyName locks -NotePropertyValue ([pscustomobject]@{
                    probe = [pscustomobject]@{
                        engine = $probeLock.engine
                        model  = $probeLock.model
                        reason = 'user lock'
                    }
                }) -Force
            ($standing | ConvertTo-Json -Depth 12) | Set-Content -Path $jsonPath -Encoding utf8
            Write-Log "Applied standing lock: probe -> $($probeLock.engine) / $($probeLock.model)"
        } catch {
            Write-Log "WARN: failed to enforce probe lock: $_"
        }
    }

    # 3) Publish latest + history
    Copy-Item $briefPath (Join-Path $OutRoot 'latest.md') -Force
    Copy-Item $jsonPath (Join-Path $OutRoot 'latest.json') -Force
    $histLine = (@{
            ts       = (Get-Date).ToString('o')
            run_dir  = $RunDir
            provider = $providerUsed
            projects = $collect.ProjectCount
        } | ConvertTo-Json -Compress)
    Add-Content -Path (Join-Path $OutRoot 'history.jsonl') -Value $histLine -Encoding utf8

    Write-Log "Published latest.md latest.json"
    Write-Log "DONE exit 0"
    exit 0
} catch {
    Write-Log "FAIL: $_"
    Write-Log $_.ScriptStackTrace
    exit 1
}
