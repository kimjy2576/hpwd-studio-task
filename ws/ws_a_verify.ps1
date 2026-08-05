# WS-A — feat/analytic-medium v1 (73a7b24 동결) 600s symbolic 검증
# 사용:  powershell -ExecutionPolicy Bypass -File ws\ws_a_verify.ps1
# 런 3개: sym.r1 / sym.r2 (재현성) / symT16.r1 (-jacobianThreads=16 이득 측정)
# 기대: 드리프트 ±0.04% (기호 야코비안), 야코비안이 런타임 85% 였으므로 wall 대폭 단축 기대
$ErrorActionPreference = "Continue"
$MAINREPO = (Resolve-Path "$PSScriptRoot\..").Path
$TREE = Join-Path $env:TEMP "wsa_tree"
$W    = Join-Path $env:TEMP "wsa_verify"
$MODEL = "HPWDcycle.Cycle_L3_coldstart_charge"
$REF  = "73a7b24"
$TMO  = 2400
New-Item -ItemType Directory -Force -Path $W | Out-Null

# ── v1 동결 스냅샷 워크트리 ───────────────────────────────────────
Set-Location $MAINREPO
if (-not (Test-Path "$TREE\modelica")) {
  git worktree add --detach $TREE $REF
  if (-not (Test-Path "$TREE\modelica")) { Write-Host "worktree 실패 — git fetch 후 재시도"; exit 1 } }
$REPO = $TREE -replace '\\','/'
Set-Location $W

# ── omc 탐지 ──────────────────────────────────────────────────────
$OMC = (Get-Command omc -ErrorAction SilentlyContinue).Source
if (-not $OMC -and $env:OPENMODELICAHOME) {
  $c = Join-Path $env:OPENMODELICAHOME "bin\omc.exe"; if (Test-Path $c) { $OMC = $c } }
if (-not $OMC) {
  $c = Get-ChildItem "C:\Program Files\OpenModelica*\bin\omc.exe" -ErrorAction SilentlyContinue |
       Sort-Object FullName -Descending | Select-Object -First 1
  if ($c) { $OMC = $c.FullName } }
if (-not $OMC) { Write-Host "omc 없음 — OpenModelica 설치 필요"; exit 1 }
Write-Host "[omc] $OMC"
$env:Path = (Split-Path $OMC) + ";" + $env:Path

# ── 빌드 (symbolic 야코비안) ──────────────────────────────────────
$mos = @"
setCommandLineOptions("--generateDynamicJacobian=symbolic"); getErrorString();
loadModel(Modelica); getErrorString();
loadFile("$REPO/modelica/R290Tab.mo"); getErrorString();
loadFile("$REPO/modelica/R290Medium.mo"); getErrorString();
loadFile("$REPO/modelica/R290Oil.mo"); getErrorString();
loadFile("$REPO/modelica/HXGeom.mo"); getErrorString();
loadFile("$REPO/modelica/HXCorr.mo"); getErrorString();
loadFile("$REPO/modelica/HPWD.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDon.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDevap.mo"); getErrorString();
loadFile("$REPO/modelica/Control.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDcycle.mo"); getErrorString();
b := buildModel($MODEL, stopTime=600, tolerance=1e-3, method="dassl",
  outputFormat="csv",
  variableFilter="time|M_total|Pc_bar|Pe_bar|SH|eevctl.n_pulse|seq.f|comp.h_dis");
print("EXE=" + b[1] + "|\n"); print(getErrorString());
"@
Set-Content -Path "$W\build.mos" -Value $mos -Encoding UTF8
Remove-Item "$W\$MODEL.exe" -ErrorAction SilentlyContinue
Write-Host "[build] omc (symbolic)..."
& $OMC build.mos *> build.log
if (-not (Test-Path "$W\$MODEL.exe")) {
  Write-Host "빌드 실패 — build.log 마지막 20줄:"; Get-Content "$W\build.log" -Tail 20; exit 1 }

# ── 런 정의 ───────────────────────────────────────────────────────
$RUNS = [ordered]@{
  "sym.r1"     = @("-jacobian=coloredSymbolical")
  "sym.r2"     = @("-jacobian=coloredSymbolical")
  "symT16.r1"  = @("-jacobian=coloredSymbolical","-jacobianThreads=16")
}

# ── 병렬 발사 ─────────────────────────────────────────────────────
$procs = @()
foreach ($name in $RUNS.Keys) {
  $d = "$W\$name"; New-Item -ItemType Directory -Force -Path $d | Out-Null
  Copy-Item "$W\$MODEL*" $d -Force -ErrorAction SilentlyContinue
  $sp = @{ FilePath = "$d\$MODEL.exe"; WorkingDirectory = $d
           WindowStyle = "Hidden"; PassThru = $true
           RedirectStandardOutput = "$d\run.log"; RedirectStandardError = "$d\err.log" }
  if ($RUNS[$name].Count -gt 0) { $sp.ArgumentList = $RUNS[$name] }
  $p = Start-Process @sp
  $procs += [pscustomobject]@{ P=$p; Dir=$d; Name=$name; T0=Get-Date }
  Write-Host ("발사  {0,-11}  PID {1}" -f $name, $p.Id)
}

# ── 감시 ──────────────────────────────────────────────────────────
while ($procs | Where-Object { -not $_.P.HasExited }) {
  Start-Sleep -Seconds 20
  foreach ($j in $procs | Where-Object { -not $_.P.HasExited }) {
    if (((Get-Date) - $j.T0).TotalSeconds -gt $TMO) { $j.P.Kill(); Write-Host "타임아웃 kill: $($j.Name)" } }
}
foreach ($j in $procs) {
  $et = if ($j.P.ExitTime) { $j.P.ExitTime } else { Get-Date }
  $sec = [int](($et - $j.T0).TotalSeconds)
  Set-Content "$($j.Dir)\done.txt" "RC=$($j.P.ExitCode) WALL=${sec}s" }
Write-Host "[run] 종료"

# ── 판정 ──────────────────────────────────────────────────────────
$PY = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
$out = @("=== WS-A v1 symbolic $(Get-Date -Format 'yyyy-MM-dd HH:mm') · OMC $(Split-Path (Split-Path $OMC)) ===",
         "런 | RC/wall | t_end | judge")
foreach ($j in $procs) {
  $csv = "$($j.Dir)\${MODEL}_res.csv"
  $rcw = if (Test-Path "$($j.Dir)\done.txt") { Get-Content "$($j.Dir)\done.txt" } else { "?" }
  if (Test-Path $csv) {
    $te = ((Get-Content $csv -Tail 1) -split ',')[0]
    $jg = (& $PY "$MAINREPO/ws/judge.py" $csv 2>$null)
  } else {
    $te = "-"
    $e1 = if (Test-Path "$($j.Dir)\err.log") { Get-Content "$($j.Dir)\err.log" -TotalCount 1 } else { "" }
    $r1 = if (Test-Path "$($j.Dir)\run.log") { (Get-Content "$($j.Dir)\run.log" | Select-Object -First 3) -join " / " } else { "" }
    $jg = "CSV 없음 | err: $e1 | run: $r1" }
  $out += "--- $($j.Name) | $rcw | t=$te"
  $out += $jg
}
$out | Tee-Object -FilePath "$W\summary.txt"
Write-Host ""
Write-Host "기대: sym r1/r2 완주 + 드리프트 |<=0.04%|. symT16 은 wall 비교용."
Write-Host "회신: $W\summary.txt 내용."
