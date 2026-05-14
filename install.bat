@echo off
echo.
echo  ============================================
echo   ViewNet -- Instalacion de dependencias
echo  ============================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python no encontrado. Instala Python 3.11+ desde python.org
    pause
    exit /b 1
)

echo  Instalando dependencias Python...
pip install scapy pysnmp netmiko psutil

echo.
echo  ============================================
echo   IMPORTANTE para Windows:
echo   Scapy requiere Npcap para captura de paquetes.
echo   Descargalo desde: https://npcap.com
echo   Instalar con la opcion "WinPcap API compatibility"
echo  ============================================
echo.
echo  Instalacion completada!
echo  Ejecutar ViewNet:  python main.py
echo.
pause
