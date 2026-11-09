@echo off
title SGI RSC - commit e push
cd /d "%~dp0"
if exist "_claude_git_status.bat" del "_claude_git_status.bat"

echo Arquivos alterados (o que vai entrar no commit):
echo.
git status --short
echo.
echo Confira a lista acima. Pressione uma tecla para fazer commit e push,
echo ou feche esta janela para cancelar.
pause >nul

git add -A
if errorlevel 1 goto erro

git commit -m "Atualizacoes do SGI (07/11/2026)" ^
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" ^
  -m "Claude-Session: https://claude.ai/code/session_01TDTxUpGbobmZvxzP3CBKvE"
if errorlevel 1 goto erro

git push origin main
if errorlevel 1 goto erro

echo.
echo OK: commit enviado para o GitHub (main).
pause
exit /b 0

:erro
echo.
echo Deu erro (ou nao havia nada para commitar). Veja a mensagem acima.
pause
exit /b 1
