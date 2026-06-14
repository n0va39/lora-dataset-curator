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
    --name "LoRA-Dataset-Curator" `
    --specpath "build" `
    --paths "src" `
    "scripts/entrypoint.py"

  & ".\dist\LoRA-Dataset-Curator.exe" --help | Out-Null
  & ".\dist\LoRA-Dataset-Curator.exe" gui --help | Out-Null
  & ".\dist\LoRA-Dataset-Curator.exe" duplicates --help | Out-Null
  Write-Host "Build complete: dist/LoRA-Dataset-Curator.exe"
}
finally {
  Pop-Location
}
