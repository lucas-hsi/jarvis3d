@echo off
rem Gera o instalador do Jarvis: 1) servidor Python (PyInstaller)  2) casca Electron + instalador NSIS (electron-builder).
rem Resultado: desktop\dist\JarvisSetup-<versao>.exe  (+ latest.yml e .blockmap, usados na atualizacao automatica)
rem Antes de publicar uma versao nova: suba "version" em desktop\package.json.
rem Python: usa JARVIS_PY se definido, senao .venv\Scripts\python.exe, senao o "python" do PATH (precisa das dependencias de empacotar\requirements-lock.txt e do pyinstaller).
cd /d "%~dp0.."
set PYTHONUTF8=1
if not defined JARVIS_PY (
  if exist ".venv\Scripts\python.exe" (set "JARVIS_PY=.venv\Scripts\python.exe") else (set "JARVIS_PY=python")
)
echo [1/2] Empacotando o servidor Python...
"%JARVIS_PY%" -m PyInstaller empacotar\jarvis-server.spec --noconfirm --distpath dist-server --workpath build-server || exit /b 1
echo [2/2] Gerando o instalador...
cd desktop
if not exist node_modules call npm ci || exit /b 1
call npm run dist || exit /b 1
echo.
echo Pronto: desktop\dist\
