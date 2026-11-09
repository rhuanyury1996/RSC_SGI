@echo off
title SGI RSC - desfazer juncao
cd /d "%~dp0"
git rebase --abort
git status --short --branch
git log --oneline -3
echo.
echo Pronto: pasta voltou como estava antes da juncao.
pause
