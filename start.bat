@echo off
chcp 65001 >nul
title PBRForge::Core v0.2

echo.
echo  ============================================
echo    PBRForge::Core v0.2  -  Ishga tushish
echo  ============================================
echo.
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:8000
echo  API Docs : http://localhost:8000/docs
echo  ComfyUI  : http://localhost:8188
echo.

:: Python tekshirish
where python >nul 2>&1
if errorlevel 1 (
    echo  [XATO] Python topilmadi. Python 3.10+ o'rnating.
    pause & exit /b 1
)

:: Node.js tekshirish
where node >nul 2>&1
if errorlevel 1 (
    echo  [XATO] Node.js topilmadi. Node 18+ o'rnating.
    pause & exit /b 1
)

:: .env tekshirish
if not exist "%~dp0backend\.env" (
    if exist "%~dp0backend\.env.example" (
        copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
        echo  [INFO] .env yaratildi. CHECKPOINT_NAME ni to'g'rilang!
        echo.
    )
)

:: Python paketlar
python -c "import fastapi, cv2" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Python paketlar o'rnatilmoqda...
    pip install -r "%~dp0backend\requirements.txt"
    echo.
)

:: Node paketlar
if not exist "%~dp0frontend\node_modules" (
    echo  [INFO] npm paketlar o'rnatilmoqda...
    pushd "%~dp0frontend"
    npm install
    popd
    echo.
)

:: Backend — alohida oynada
echo  [1/2] Backend ishga tushirilmoqda (port 8000)...
start "PBRForge Backend" cmd /k "cd /d "%~dp0backend" && python main.py"

:: 2 soniya kutish (backend yoqilguncha)
timeout /t 2 /nobreak >nul

:: Frontend — alohida oynada
echo  [2/2] Frontend ishga tushirilmoqda (port 5173)...
start "PBRForge Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: Brauzer
timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo  Ikkala oynani yopish uchun Ctrl+C bosing.
echo.
