<#
  Starts the pinned llama.cpp Vulkan server that serves the real
  ai21labs/AI21-Jamba2-3B model as its pinned GGUF build.

  Docker Desktop cannot pass a Radeon GPU into a Linux container, so this
  server runs on the host and the `llm` service reaches it through
  compose.llm.gguf.yaml.  Every artifact is pinned and SHA256-verified: this
  lane serves the real model, never a mock.

  The server has no authentication and must bind 0.0.0.0 so the container can
  reach it through host.docker.internal.  Keep the Windows Firewall profile on
  Private, or pass -ApiKey and set LLAMA_API_KEY for the container.
#>
param(
  [string]$Root = "",
  [int]$Port = 8090,
  [int]$ContextSize = 16384,
  [int]$GpuLayers = 99,
  [string]$ApiKey = "",
  [switch]$SkipVerify,
  [switch]$ListDevicesOnly
)

$ErrorActionPreference = "Stop"

# Pinned artifacts.  Change these only together with the documented pins in
# .env.example, compose.llm.gguf.yaml, and services/llm/app.py.
$Build = "b10647"
$ZipName = "llama-$Build-bin-win-vulkan-x64.zip"
$ZipSha256 = "0300643b1479bac0eda015f9a00c564217b60856d2cf4c72b0e9fa6b1a5b0133"
$ZipUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$Build/$ZipName"
$GgufRepo = "bartowski/ai21labs_AI21-Jamba2-3B-GGUF"
$GgufRevision = "02d70acd708332ec4e78e9ceefe116851a307411"
$GgufName = "ai21labs_AI21-Jamba2-3B-Q8_0.gguf"
$GgufSha256 = "2c624f1d663d2d9e1008d718c3e8d67ae62a19733ddde89ee90872e0c84eb50b"
$GgufUrl = "https://huggingface.co/$GgufRepo/resolve/$GgufRevision/$GgufName"
$ModelAlias = "ai21labs/AI21-Jamba2-3B"

if (-not $Root) {
  if ($env:COREAIGENT_GGUF_ROOT) { $Root = $env:COREAIGENT_GGUF_ROOT }
  else { $Root = Join-Path $HOME ".coreaigent\gguf" }
}

function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
  if ($SkipVerify) { Write-Host "Skipping SHA256 verification of $Label"; return }
  $actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $Expected) {
    throw "$Label failed SHA256 verification. Expected $Expected but found $actual. Refusing to serve an unpinned artifact."
  }
  Write-Host "Verified $Label"
}

function Get-PinnedFile([string]$Url, [string]$Destination, [string]$Label) {
  $partial = "$Destination.part"
  if (Test-Path $partial) { Remove-Item -Force $partial }
  Write-Host "Downloading $Label"
  if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
    & curl.exe -L --fail --retry 3 --output $partial $Url
    if ($LASTEXITCODE -ne 0) { throw "Download of $Label failed with exit code $LASTEXITCODE" }
  } else {
    $previous = $ProgressPreference; $ProgressPreference = "SilentlyContinue"
    try { Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing } finally { $ProgressPreference = $previous }
  }
  Move-Item -Force $partial $Destination
}

$BuildDir = Join-Path $Root "llama.cpp\$Build"
$ModelDir = Join-Path $Root "models"
$ZipPath = Join-Path $Root "llama.cpp\$ZipName"
$ModelPath = Join-Path $ModelDir $GgufName
$ServerExe = Join-Path $BuildDir "llama-server.exe"

New-Item -ItemType Directory -Force -Path (Join-Path $Root "llama.cpp") | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

if (-not (Test-Path $ServerExe)) {
  if (-not (Test-Path $ZipPath)) { Get-PinnedFile $ZipUrl $ZipPath "llama.cpp $Build Vulkan build" }
  Assert-Sha256 $ZipPath $ZipSha256 "llama.cpp $Build Vulkan build"
  New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
  Expand-Archive -Path $ZipPath -DestinationPath $BuildDir -Force
  if (-not (Test-Path $ServerExe)) {
    $found = Get-ChildItem -Path $BuildDir -Filter "llama-server.exe" -Recurse | Select-Object -First 1
    if ($null -eq $found) { throw "llama-server.exe is missing from $ZipName" }
    $ServerExe = $found.FullName
  }
}

if (-not (Test-Path $ModelPath)) { Get-PinnedFile $GgufUrl $ModelPath "$GgufName" }
Assert-Sha256 $ModelPath $GgufSha256 "$GgufName"

Write-Host "llama.cpp build: $ServerExe"
Write-Host "Pinned GGUF:     $ModelPath"
& $ServerExe --list-devices
if ($ListDevicesOnly) { exit 0 }

$serverArgs = @(
  "--model", $ModelPath,
  "--alias", $ModelAlias,
  "--host", "0.0.0.0",
  "--port", "$Port",
  "--ctx-size", "$ContextSize",
  "--n-gpu-layers", "$GpuLayers",
  "--parallel", "1",
  "--jinja"
)
if ($ApiKey) { $serverArgs += @("--api-key", $ApiKey) }

Write-Host ""
Write-Host "Serving $ModelAlias on http://0.0.0.0:$Port (no authentication unless -ApiKey is set)."
Write-Host "Containers reach it as http://host.docker.internal:$Port."
Write-Host ""
& $ServerExe @serverArgs
