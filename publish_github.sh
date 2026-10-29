#!/usr/bin/env bash
set -euo pipefail
command -v gh >/dev/null || { echo 'Install GitHub CLI: https://cli.github.com/'; exit 1; }
command -v git >/dev/null || { echo 'Git is required'; exit 1; }
gh auth status || gh auth login
[[ -d .git ]] || git init -b main
git add .
git commit -m 'Initial Bethorahzan community platform'
gh repo create Bethorahzan --private --source . --remote origin --push
