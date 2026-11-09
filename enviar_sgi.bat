@echo off
title SGI RSC - enviar para o GitHub
cd /d "%~dp0"

echo [1/3] Salvando alteracoes pendentes...
git add -A
git diff --cached --quiet || git commit -m "Ajustes SGI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01XpEhLw7UF1n9GJUCtGGPZN"

echo [2/3] Juntando com a versao do GitHub...
git pull --rebase origin main
if errorlevel 1 (
  echo.
  echo CONFLITO ao juntar com o GitHub. Nada foi enviado.
  echo Para desfazer e voltar como estava: git rebase --abort
  git status --short
  pause & exit /b 1
)

echo [3/3] Enviando...
git push origin main
if errorlevel 1 (
  echo.
  echo Falha no push. Veja a mensagem acima.
  pause & exit /b 1
)

echo.
echo OK: nova versao no GitHub (main). Render vai fazer o deploy.
git log --oneline -3
pause
