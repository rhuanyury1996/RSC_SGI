@echo off
title SGI RSC - localhost
cd /d "%~dp0"
set "PGBIN=C:\Program Files\PostgreSQL\18\bin"
set "PGDATA=%~dp0.pgdata"

if not exist "%PGBIN%\pg_ctl.exe" (
  echo ERRO: nao achei "%PGBIN%\pg_ctl.exe"
  pause & exit /b 1
)

echo [1/2] Verificando banco na porta 5433...
netstat -ano | findstr /R /C:"127.0.0.1:5433 .*LISTENING" >nul
if errorlevel 1 (
  echo Banco desligado. Limpando trava antiga e ligando...
  if exist "%PGDATA%\postmaster.pid" del /f "%PGDATA%\postmaster.pid"
  "%PGBIN%\pg_ctl.exe" start -D "%PGDATA%" -o "-p 5433" -l "%PGDATA%\pg.log" -w -t 30
  if errorlevel 1 (
    echo ERRO ao ligar o banco. Ultimas linhas do log:
    powershell -NoProfile -Command "Get-Content -Tail 15 '%PGDATA%\pg.log'"
    pause & exit /b 1
  )
) else (
  echo Banco ja ligado.
)

echo [2/2] Subindo SGI em http://127.0.0.1:8000 ...
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000/admin/"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
echo.
echo Servidor parou. Veja o erro acima.
pause
