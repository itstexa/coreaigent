param(
  [Parameter(Position = 0, Mandatory = $true)]
  [ValidateSet("dev", "integration", "e2e", "test", "logs", "reset", "validate")]
  [string]$Command,
  [Parameter(Position = 1)]
  [string]$Service
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Services = @("ocr", "classification", "validation", "rag", "llm", "workflow")
$TopologyRegistry = Get-Content (Join-Path $PSScriptRoot "local-topologies.json") -Raw | ConvertFrom-Json
Set-Location $Root

function Assert-Service([string]$Name) {
  if ($Name -notin $Services) { throw "Service must be one of: $($Services -join ', ')" }
}
function Assert-Dockerfile([string]$Name) {
  if (-not (Test-Path "services/$Name/Dockerfile")) { throw "services/$Name/Dockerfile is missing. A mock cannot be started as a real $Name service." }
}
function Get-LocalTopology([string]$Name) {
  $Topology = $TopologyRegistry.topologies.$Name
  if ($null -eq $Topology) { throw "No local topology is declared for $Name. A mock cannot be presented as a full real local topology." }
  foreach ($ComposeFile in $Topology.compose_files) {
    if (-not (Test-Path $ComposeFile)) { throw "Required Compose overlay $ComposeFile is missing for local $Name." }
  }
  foreach ($LocalService in $Topology.local_services) { Assert-Dockerfile $LocalService }
  if ($Topology.verification_kind -eq "real_local" -and $Topology.missing_dependencies.Count -ne 0) { throw "Local $Name topology declares missing dependencies but is marked real_local." }
  return $Topology
}
function Write-Topology([string]$Name, $Topology) {
  Write-Host "Local topology for $Name: $($Topology.verification_kind)"
  if ($Topology.missing_dependencies.Count -ne 0) { Write-Host "Mixed dependencies: $($Topology.missing_dependencies -join ', ')" }
}
function Write-LocalOverride([string]$Name) {
  @"
services:
  ${Name}:
    build:
      context: ./services/$Name
    image: coreaigent/${Name}:local
"@ | Set-Content -NoNewline .compose.local.generated.yml
}
function Invoke-Compose([string[]]$ComposeFiles, [string[]]$ComposeArguments) {
  $fileArgs = @(); foreach ($file in $ComposeFiles) { $fileArgs += "-f"; $fileArgs += $file }
  & docker compose @fileArgs @ComposeArguments
}
switch ($Command) {
  "dev" {
    Assert-Service $Service; Assert-Dockerfile $Service; $Topology = Get-LocalTopology $Service; Write-Topology $Service $Topology
    Invoke-Compose -ComposeFiles $Topology.compose_files -ComposeArguments @("up", "--build", "-d")
  }
  "integration" {
    Assert-Service $Service; Assert-Dockerfile $Service; Write-LocalOverride $Service
    $Files = @("compose.yaml", "compose.integration.yaml")
    if ($Service -eq "llm") { $Files += "compose.llm.yaml" }
    if ($Service -eq "ocr") { $Files += "compose.ocr.yaml" }
    $Files += ".compose.local.generated.yml"
    Invoke-Compose -ComposeFiles $Files -ComposeArguments @("up", "--build", "-d")
  }
  "e2e" { Invoke-Compose -ComposeFiles @("compose.yaml", "compose.integration.yaml") -ComposeArguments @("up", "-d") }
  "test" {
    $Mode = $Service
    $Local = $args[0]
    if ($Mode -notin @("mock", "development", "integration", "e2e")) { throw "Usage: test mock | test development <service> | test integration <service> | test e2e" }
    $Files = @("compose.yaml")
    $TestArgs = @("--profile", "tests", "run", "--build", "--rm", "contract-tests")
    if ($Mode -eq "mock") { $TestArgs += @("--mode", "mock") }
    elseif ($Mode -eq "development") { Assert-Service $Local; Assert-Dockerfile $Local; $Topology = Get-LocalTopology $Local; Write-Topology $Local $Topology; $Files = @($Topology.compose_files); $TestArgs = @("--profile", "tests", "run", "--build", "--rm", "--entrypoint", "python", "contract-tests") + @($Topology.acceptance_runner) }
    elseif ($Mode -eq "integration") { Assert-Service $Local; Assert-Dockerfile $Local; Write-LocalOverride $Local; $Files += "compose.integration.yaml"; if ($Local -eq "llm") { $Files += "compose.llm.yaml" }; if ($Local -eq "ocr") { $Files += "compose.ocr.yaml" }; $Files += ".compose.local.generated.yml"; $TestArgs += @("--mode", "real") }
    else { $Files += "compose.integration.yaml"; $TestArgs += @("--mode", "real") }
    Invoke-Compose -ComposeFiles $Files -ComposeArguments $TestArgs
  }
  "logs" { Invoke-Compose -ComposeFiles @("compose.yaml") -ComposeArguments @("logs", "-f", "--tail", "100") }
  "reset" { Invoke-Compose -ComposeFiles @("compose.yaml", "compose.ocr.yaml") -ComposeArguments @("down", "--volumes", "--remove-orphans"); Remove-Item .compose.local.generated.yml -Force -ErrorAction SilentlyContinue }
  "validate" { & docker build -f tests/Dockerfile -t coreaigent/contract-tests:1.0 .; & docker run --rm --entrypoint python coreaigent/contract-tests:1.0 /app/validate_contracts.py }
}
