@echo off
title SGI RSC - finalizar envio
cd /d "%~dp0"
set GIT_EDITOR=true

git add templates/base.html
git rebase --continue
if errorlevel 1 (
  echo.
  echo Ainda ha conflito. Veja acima. Para desfazer tudo: git rebase --abort
  git status --short
  pause & exit /b 1
)

git push origin main
if errorlevel 1 (
  echo.
  echo Falha no push. Veja acima.
  pause & exit /b 1
)

echo.
echo OK: versao nova no GitHub (main).
git log --oneline -4
pause
