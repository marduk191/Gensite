@echo off
setlocal
set "SETUP_TRIED="
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" goto verify
:setup
if defined SETUP_TRIED goto failed
set "SETUP_TRIED=1"
set "UV="
for /f "delims=" %%U in ('where uv.exe 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV goto missinguv
if exist "%~dp0.venv\Scripts\python.exe" goto dependencies
echo Creating the Gensite project-local Python 3.12 environment...
"%UV%" venv --python 3.12 "%~dp0.venv"
if errorlevel 1 goto failed
:dependencies
echo Installing the Gensite native desktop runtime into .venv...
"%UV%" pip install --python "%~dp0.venv\Scripts\python.exe" -r "%~dp0requirements.txt"
if errorlevel 1 goto failed
:verify
"%~dp0.venv\Scripts\python.exe" -c "import PySide6.QtWidgets, PySide6.QtSvg; import importlib.util; assert importlib.util.find_spec('PySide6.QtWebEngineWidgets')" >nul 2>&1
if errorlevel 1 goto setup
"%~dp0.venv\Scripts\python.exe" -m gensite.native_launcher >nul
if errorlevel 1 goto failed
if "%~1"=="--check" goto check
start "" /d "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" -m gensite %*
exit /b 0
:check
"%~dp0.venv\Scripts\python.exe" -m gensite --check
exit /b %errorlevel%
:missinguv
echo Gensite needs uv to create its local Python 3.12 environment.
echo Install uv from https://docs.astral.sh/uv/getting-started/installation/ and retry.
goto errorend
:failed
echo Native runtime setup failed. The actual installation error appears above.
echo Check network and disk permissions, then run Start Gensite.bat again.
:errorend
if not "%~1"=="--check" pause
exit /b 1
