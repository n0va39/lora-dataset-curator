$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")

Push-Location $RepoRoot
try {
  uv sync --extra gui --extra image --extra build --extra dev
  uv run pytest
  uv run pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "LoRA-Dataset-Curator" `
    --specpath "build" `
    --paths "src" `
    "scripts/entrypoint.py"

  $ExePath = Join-Path $RepoRoot "dist\LoRA-Dataset-Curator.exe"
  if (-not (Test-Path $ExePath)) {
    throw "Build failed: $ExePath was not created."
  }
  Write-Host "Build complete: dist/LoRA-Dataset-Curator.exe"
}
finally {
  Pop-Location
}
