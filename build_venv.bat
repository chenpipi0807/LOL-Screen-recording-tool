@echo off
chcp 65001 >nul
echo ========================================
echo Create clean virtual environment and build
echo ========================================

REM Delete old virtual environment
if exist venv rmdir /s /q venv

REM Create new virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install required dependencies
echo Installing dependencies...
pip install PyQt5 opencv-python numpy mss imageio imageio-ffmpeg Pillow pyinstaller sounddevice soundfile pyaudiowpatch -q

REM Build
echo Starting build...
pyinstaller --clean screen_recorder.spec

echo ========================================
echo Build complete! EXE file is in dist folder
echo ========================================
pause
