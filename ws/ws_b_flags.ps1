# WS-B 플래그 매트릭스 — Windows PowerShell 판 (G2 위임, 2026-08-04)
# 사용:  레포 루트에서   powershell -ExecutionPolicy Bypass -File ws\ws_b_flags.ps1
# 전제:  omc 가 PATH 에 있음 (OpenModelica 설치 시 기본).  python 도 PATH.
# 산출:  $env:TEMP\wsb_flags\summary.txt

$ErrorActionPreference = "Continue"
$REPO  = (Resolve-Path "$PSScriptRoot\..").Path -replace '\\','/'
$W     = Join-Path $env:TEMP "wsb_flags"
$MODEL = "HPWDcycle.Cycle_L3C_coldstart_charge"
$STOP  = 600
$TMO   = 2400      # 런당 40분 상한 [s]
$REPS  = 2
New-Item -ItemType Directory -Force -Path $W | Out-Null
Set-Location $W

# ── omc 탐지 (PATH → OPENMODELICAHOME → Program Files) ────────────
$OMC = (Get-Command omc -ErrorAction SilentlyContinue).Source
if (-not $OMC -and $env:OPENMODELICAHOME) {
  $c = Join-Path $env:OPENMODELICAHOME "bin\omc.exe"
  if (Test-Path $c) { $OMC = $c } }
if (-not $OMC) {
  $c = Get-ChildItem "C:\Program Files\OpenModelica*\bin\omc.exe" -ErrorAction SilentlyContinue |
       Sort-Object FullName -Descending | Select-Object -First 1
  if ($c) { $OMC = $c.FullName } }
if (-not $OMC) {
  Write-Host "omc 를 찾지 못했습니다. OpenModelica(1.27 권장)가 설치되어 있습니까?"
  Write-Host "설치되어 있다면 PowerShell 에서  \$env:OPENMODELICAHOME  경로를 알려주십시오."
  Write-Host "미설치라면 https://openmodelica.org/download → Windows 64bit 설치 후 재실행."
  exit 1 }
Write-Host "[omc] $OMC"
$env:Path = (Split-Path $OMC) + ";" + $env:Path   # 시뮬 exe 가 OM 런타임 DLL 을 찾도록

# ── 1회 빌드 ──────────────────────────────────────────────────────
$mos = @"
loadModel(Modelica); getErrorString();
loadFile("$REPO/modelica/R290Tab.mo"); getErrorString();
loadFile("$REPO/modelica/R290Medium.mo"); getErrorString();
loadFile("$REPO/modelica/R290Oil.mo"); getErrorString();
loadFile("$REPO/modelica/HXGeom.mo"); getErrorString();
loadFile("$REPO/modelica/HXCorr.mo"); getErrorString();
loadFile("$REPO/modelica/HPWD.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDon.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDevap.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDevapC.mo"); getErrorString();
loadFile("$REPO/modelica/Control.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDcycle.mo"); getErrorString();
b := buildModel($MODEL, stopTime=$STOP, tolerance=1e-3,
  method="dassl", outputFormat="csv",
  variableFilter="time|M_total|Pc_bar|Pe_bar|SH|eevctl.n_pulse|seq.f|comp.h_dis");
print("EXE=" + b[1] + "|\n"); print(getErrorString());
"@
Set-Content -Path "$W\build.mos" -Value $mos -Encoding UTF8
if (-not (Test-Path "$W\$MODEL.exe")) {
  Write-Host "[build] omc..." ; & $OMC build.mos *> build.log
}
if (-not (Test-Path "$W\$MODEL.exe")) {
  Write-Host "빌드 실패 — $W\build.log 마지막 20줄:"
  if (Test-Path "$W\build.log") { Get-Content "$W\build.log" -Tail 20 }
  exit 1 }

# ── 조합 ──────────────────────────────────────────────────────────
$CFGS = [ordered]@{
  base       = @()
  noeq       = @("-noEquidistantTimeGrid")
  nores      = @("-noRestart")
  noeq_nores = @("-noEquidistantTimeGrid","-noRestart")
  ida        = @("-s=ida")
  cvode      = @("-s=cvode")
}

# ── 병렬 발사 ─────────────────────────────────────────────────────
$procs = @()
foreach ($name in $CFGS.Keys) {
  for ($r = 1; $r -le $REPS; $r++) {
    $d = "$W\$name.r$r"
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    Copy-Item "$W\$MODEL*" $d -Force -ErrorAction SilentlyContinue
    $sp = @{ FilePath = "$d\$MODEL.exe"; WorkingDirectory = $d
             WindowStyle = "Hidden"; PassThru = $true
             RedirectStandardOutput = "$d\run.log"
             RedirectStandardError  = "$d\err.log" }
    if ($CFGS[$name].Count -gt 0) { $sp.ArgumentList = $CFGS[$name] }
    $p = Start-Process @sp
    $procs += [pscustomobject]@{ P=$p; Dir=$d; Name="$name.r$r"; T0=Get-Date }
    Write-Host ("발사  {0,-14}  PID {1}" -f "$name.r$r", $p.Id)
  }
}

# ── 감시 (완료/타임아웃) ──────────────────────────────────────────
while ($procs | Where-Object { -not $_.P.HasExited }) {
  Start-Sleep -Seconds 20
  foreach ($j in $procs | Where-Object { -not $_.P.HasExited }) {
    $el = ((Get-Date) - $j.T0).TotalSeconds
    if ($el -gt $TMO) { $j.P.Kill(); Write-Host "타임아웃 kill: $($j.Name)" }
  }
}
foreach ($j in $procs) {
  $sec = [int]((Get-Date) - $j.T0).TotalSeconds
  Set-Content "$($j.Dir)\done.txt" "RC=$($j.P.ExitCode) WALL=${sec}s"
}
Write-Host "[run] 전 조합 종료"

# ── 판정 집계 ─────────────────────────────────────────────────────
$PY = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
$out = @("=== WS-B 플래그 매트릭스 $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===",
         "조합 | RC/wall | t_end | judge")
foreach ($j in $procs) {
  $csv = "$($j.Dir)\${MODEL}_res.csv"
  $rcw = if (Test-Path "$($j.Dir)\done.txt") { Get-Content "$($j.Dir)\done.txt" } else { "?" }
  if (Test-Path $csv) {
    $te = ((Get-Content $csv -Tail 1) -split ',')[0]
    $jg = (& $PY "$REPO/ws/judge.py" $csv 2>$null | Select-Object -First 1)
  } else { $te = "-"
    $e1 = if (Test-Path "$($j.Dir)\err.log") { (Get-Content "$($j.Dir)\err.log" -TotalCount 1) } else { "" }
    $r1 = if (Test-Path "$($j.Dir)\run.log") { (Get-Content "$($j.Dir)\run.log" -Tail 1) } else { "" }
    $jg = "CSV 없음 | err: $e1 | run: $r1" }
  $out += "$($j.Name) | $rcw | t=$te | $jg"
}
$out | Tee-Object -FilePath "$W\summary.txt"
Write-Host ""
Write-Host "판정: 두 rep 모두 t=600 완주 + 드리프트 |<=0.4%| 조합 = 처방 확정."
Write-Host "회신: $W\summary.txt 내용 붙여넣기."
