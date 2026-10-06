param([Parameter(Position=0,Mandatory=$true)][string]$Command,[Parameter(Position=1)][string]$Argument,[string]$VaultPath="$PSScriptRoot\..\work\demo-vault",[string]$Mode='hybrid',[int]$TopK=6)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path "$PSScriptRoot\..").Path
$Config=Join-Path ([IO.Path]::GetFullPath($VaultPath)) 'PersonalOS\.personal-os\config.yaml'
$Python=Join-Path $Root '.venv\Scripts\python.exe'
$Cli=Join-Path $Root 'src\personal_os.py'
switch($Command){
  'search' {& $Python $Cli --config $Config search $Argument --mode $Mode --top-k $TopK}
  'reflect' {& $Python $Cli --config $Config reflect --input $Argument}
  default {& $Python $Cli --config $Config $Command}
}
exit $LASTEXITCODE
