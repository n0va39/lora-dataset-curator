$ErrorActionPreference = "Stop"

uv sync --extra gui --extra image --extra build --extra dev
uv run pytest
uv run pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name "LoRA-Dataset-Curator" `
  --paths "src" `
  "scripts/entrypoint.py"

Write-Host "Build complete: dist/LoRA-Dataset-Curator.exe"
