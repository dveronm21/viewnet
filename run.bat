@echo off
:: Ejecutar ViewNet con privilegios de administrador (necesario para raw sockets)
net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando permisos de Administrador...
    powershell -Command "Start-Process python -ArgumentList 'main.py' -WorkingDirectory '%~dp0' -Verb RunAs"
) else (
    python "%~dp0main.py"
)
