$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")

function Invoke-Checked {
  param(
    [string]$Label,
    [string]$Command,
    [string[]]$Arguments
  )

  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

Push-Location $RepoRoot
try {
  $ExePath = Join-Path $RepoRoot "dist\LoRA-Dataset-Curator.exe"
  if (Test-Path $ExePath) {
    Remove-Item -Force $ExePath
  }

  Invoke-Checked "uv sync" "uv" @(
    "sync",
    "--extra", "gui",
    "--extra", "image",
    "--extra", "build",
    "--extra", "dev"
  )
  Invoke-Checked "pytest" "uv" @("run", "pytest")
  Invoke-Checked "pyinstaller" "uv" @(
    "run", "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "LoRA-Dataset-Curator",
    "--specpath", "build",
    "--paths", "src",
    "scripts/entrypoint.py"
  )

  if (-not (Test-Path $ExePath)) {
    throw "Build failed: $ExePath was not created."
  }
  Write-Host "Build complete: dist/LoRA-Dataset-Curator.exe"
}
finally {
  Pop-Location
}
