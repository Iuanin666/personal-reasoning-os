param([string]$Destination)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path "$PSScriptRoot\..").Path
if(-not $Destination){$Destination=Join-Path $Root 'work\demo-vault'}
$Destination=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $Destination){throw "Destination already exists: $Destination"}
New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent)|Out-Null
Copy-Item -LiteralPath "$Root\examples\demo-vault" -Destination $Destination -Recurse
$PosRoot=Join-Path $Destination 'PersonalOS'
foreach($dir in @('04_Knowledge\Books','04_Knowledge\Papers','04_Knowledge\Cases','04_Knowledge\Frameworks','04_Knowledge\_Sources','90_Inbox','.personal-os\index','.personal-os\cache','.personal-os\logs','.personal-os\conflicts')){New-Item -ItemType Directory -Force -Path (Join-Path $PosRoot $dir)|Out-Null}
$Config=@{
  version=2;personal_os_version='0.6.1';reflect_version='0.2.0';retrieval_baseline='Retrieval Evaluation v1.1 / synthetic public set';
  vault_path=$Destination;personal_os_root='..';database_path='.personal-os/index/memory.sqlite3';
  embedding=@{provider='local';model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';local_path=(Join-Path $Root 'models\multilingual-minilm');backend='onnx-cpu-quint8';dimensions=384};
  search=@{keyword_top_k=30;semantic_top_k=30;final_top_k=6;ranking_profile='optimized_v1'}
}
$Config|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $PosRoot '.personal-os\config.json') -Encoding utf8
@"
version: 2
personal_os_version: 0.6.1
reflect_version: 0.2.0
retrieval_baseline: Retrieval Evaluation v1.1 / synthetic public set
vault_path: $($Destination.Replace('\','/'))
personal_os_root: ..
database_path: .personal-os/index/memory.sqlite3
embedding:
  provider: local
  model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  local_path: $((Join-Path $Root 'models\multilingual-minilm').Replace('\','/'))
  backend: onnx-cpu-quint8
  dimensions: 384
search:
  keyword_top_k: 30
  semantic_top_k: 30
  final_top_k: 6
  ranking_profile: optimized_v1
"@|Set-Content -LiteralPath (Join-Path $PosRoot '.personal-os\config.yaml') -Encoding utf8
Write-Output $Destination
