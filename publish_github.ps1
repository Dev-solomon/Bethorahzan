# Execute in PowerShell from this unzipped project directory.
# Requires https://cli.github.com/ (GitHub CLI) and git.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI: https://cli.github.com/' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git: https://git-scm.com/' }
gh auth status
if ($LASTEXITCODE -ne 0) { gh auth login }
if (-not (Test-Path '.git')) { git init -b main }
git add .
git commit -m "Initial Bethorahzan community platform"
# Private by default to protect an early-stage application.
gh repo create Bethorahzan --private --source . --remote origin --push
Write-Host 'Repository created and pushed.'
