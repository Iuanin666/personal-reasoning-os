param([switch]$SkipIngest,[switch]$SkipModel)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$true
$Root=(Resolve-Path "$PSScriptRoot\..").Path
$LocalTemp=Join-Path $Root '.setup-tmp';New-Item -ItemType Directory -Force -Path $LocalTemp|Out-Null
$env:TEMP=$LocalTemp;$env:TMP=$LocalTemp
$Python=(Get-Command python -ErrorAction Stop).Source
$Version=& $Python -c "import sys;print('.'.join(map(str,sys.version_info[:2])))"
if([version]$Version -lt [version]'3.11' -or [version]$Version -ge [version]'3.14'){throw "Python 3.11-3.13 required; found $Version"}
& $Python -m venv "$Root\.venv"
$Core="$Root\.venv\Scripts\python.exe"
& $Core -m pip install --upgrade pip
& $Core -m pip install -r "$Root\requirements-lock.txt"
if(-not $SkipIngest){
  $NodeVersion=(node --version).TrimStart('v')
  if([version]$NodeVersion -lt [version]'20.19.0'){throw "Node.js 20.19+ required; found $NodeVersion"}
  & $Python -m venv "$Root\.venv-ingest"
  $Ingest="$Root\.venv-ingest\Scripts\python.exe"
  & $Ingest -m pip install --upgrade pip
  & $Ingest -m pip install -r "$Root\requirements-ingest-lock.txt"
  Push-Location "$Root\tools\defuddle"
  try { npm ci } finally { Pop-Location }
}
if(-not $SkipModel){& $Core "$Root\scripts\download_model.py"}
Write-Output "Personal OS public runtime ready at $Root"
