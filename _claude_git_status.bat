@echo off
cd /d "%~dp0"
(
echo === BRANCH ===
git branch --show-current
echo === REMOTE ===
git remote -v
echo === STATUS ===
git status --porcelain=v1 -uall
echo === DIFF STAT ===
git diff --stat
echo === UNPUSHED ===
git log --oneline @{u}..HEAD
echo === LAST COMMITS ===
git log --oneline -5
) > _claude_git_status.txt 2>&1
exit
