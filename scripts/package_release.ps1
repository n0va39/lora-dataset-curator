$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")

Push-Location $RepoRoot
try {
  $Version = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches.Groups[1].Value
  if (-not $Version) {
    throw "Could not read project version from pyproject.toml."
  }

  powershell -ExecutionPolicy Bypass -File "scripts\build_windows.ps1"

  $DistDir = Join-Path $RepoRoot "dist"
  $ExePath = Join-Path $DistDir "LoRA-Dataset-Curator.exe"
  if (-not (Test-Path $ExePath)) {
    throw "Missing build artifact: $ExePath"
  }

  $PackageRoot = Join-Path $DistDir "LoRA-Dataset-Curator-$Version"
  $ZipPath = Join-Path $DistDir "LoRA-Dataset-Curator-$Version.zip"
  if (Test-Path $PackageRoot) {
    Remove-Item -Recurse -Force $PackageRoot
  }
  if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
  }

  New-Item -ItemType Directory -Path $PackageRoot | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $PackageRoot "docs") | Out-Null

  Copy-Item $ExePath (Join-Path $PackageRoot "LoRA-Dataset-Curator.exe")
  Copy-Item "README.md" (Join-Path $PackageRoot "README.md")
  Copy-Item "RELEASE.md" (Join-Path $PackageRoot "RELEASE.md")
  Copy-Item "THIRD_PARTY_NOTICES.md" (Join-Path $PackageRoot "THIRD_PARTY_NOTICES.md")
  Copy-Item "docs\USER_GUIDE.md" (Join-Path $PackageRoot "docs\USER_GUIDE.md")
  Copy-Item "docs\BUILD_DISTRIBUTION.md" (Join-Path $PackageRoot "docs\BUILD_DISTRIBUTION.md")

  Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath
  Write-Host "Release package complete: dist/LoRA-Dataset-Curator-$Version.zip"
}
finally {
  Pop-Location
}
