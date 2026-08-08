@echo off
cd /d "%~dp0"
echo.
echo Qwen Voice Studio - Prueba local
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Falta preparar el entorno.
  echo Ejecutando instalador de dependencias...
  powershell -ExecutionPolicy Bypass -File ".\scripts\setup-windows.ps1"
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
call npm run local
pause
