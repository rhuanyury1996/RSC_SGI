@echo off
title SGI RSC - commit e push
cd /d "%~dp0"

git add funcionarios/acessos.py funcionarios/migrations/0006_acesso_modulos.py ^
  funcionarios/models.py funcionarios/admin.py funcionarios/context_processors.py ^
  funcionarios/management/commands/bootstrap_ceo.py ^
  config/settings.py config/urls.py ^
  templates/base.html templates/admin/base_site.html ^
  static/css/admin_sgi.css rodar_sgi.bat
if errorlevel 1 goto erro

git commit -m "Admin com design do SGI e controle de acesso por modulo" ^
  -m "- Admin restrito a superusuario; CEO e o unico admin no deploy" ^
  -m "- Matriz Acessos aos modulos: editar / so ver / sem acesso" ^
  -m "- Middleware bloqueia URL e escrita; menu esconde modulos sem acesso" ^
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" ^
  -m "Claude-Session: https://claude.ai/code/session_01XpEhLw7UF1n9GJUCtGGPZN"
if errorlevel 1 goto erro

git push origin main
if errorlevel 1 goto erro

echo.
echo OK: commit enviado para o GitHub (main). O Render vai fazer o deploy.
pause
exit /b 0

:erro
echo.
echo Deu erro. Veja a mensagem acima.
pause
exit /b 1
