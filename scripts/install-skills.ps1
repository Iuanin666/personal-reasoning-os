param([Parameter(Mandatory=$true)][string]$VaultPath,[string]$TargetRoot="$HOME\.codex\skills")
$ErrorActionPreference='Stop'
$Root=(Resolve-Path "$PSScriptRoot\..").Path
$Config=Join-Path ([IO.Path]::GetFullPath($VaultPath)) 'PersonalOS\.personal-os\config.yaml'
if(!(Test-Path -LiteralPath $Config)){throw "Missing Personal OS config: $Config"}
$Core=Join-Path $Root '.venv\Scripts\python.exe';$Ingest=Join-Path $Root '.venv-ingest\Scripts\python.exe'
$Defuddle=Join-Path $Root 'tools\defuddle\node_modules\.bin\defuddle.cmd'
foreach($Name in @('reflect','ingest','context','analyze','profile-review')){
  $Target=Join-Path $TargetRoot $Name
  if(Test-Path -LiteralPath $Target){throw "Target already exists; move it explicitly before install: $Target"}
  New-Item -ItemType Directory -Force -Path $TargetRoot|Out-Null
  Copy-Item -LiteralPath (Join-Path $Root "skills\$Name") -Destination $Target -Recurse
  $Runtime=@{public_release='0.1.0';config=$Config;python=$Core}
  switch($Name){
    'reflect' {$Runtime.cli=Join-Path $Root 'src\personal_os.py';$Runtime.skill_version='0.2.0'}
    'ingest' {$Runtime.cli=Join-Path $Root 'src\ingest.py';$Runtime.python=$Ingest;$Runtime.docling_python=$Ingest;$Runtime.defuddle=$Defuddle;$Runtime.index_python=$Core;$Runtime.index_cli=Join-Path $Root 'src\personal_os.py';$Runtime.skill_version='0.3.1'}
    'context' {$Runtime.cli=Join-Path $Root 'src\context_engine.py';$Runtime.skill_version='0.4.1';$Runtime.read_only=$true}
    'analyze' {$Runtime.cli=Join-Path $Root 'src\analyze.py';$Runtime.skill_version='0.5.1';$Runtime.read_only=$true}
    'profile-review' {$Runtime.cli=Join-Path $Root 'src\profile_evolution.py';$Runtime.skill_version='0.6.1';$Runtime.read_only_default=$true;$Runtime.explicit_commit_required=$true}
  }
  $Ref=Join-Path $Target 'references';New-Item -ItemType Directory -Force -Path $Ref|Out-Null
  $Runtime|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $Ref 'runtime.json') -Encoding utf8
}
Write-Output "Installed five skills under $TargetRoot"
