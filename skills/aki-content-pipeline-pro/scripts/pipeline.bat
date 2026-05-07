@echo off
REM Windows entry point for QClaw / OpenClaw on Windows
setlocal
if "%AKI_SKILLS_REPO_ROOT%"=="" set AKI_SKILLS_REPO_ROOT=%~dp0..\..\..
python "%~dp0pipeline.py" %*
