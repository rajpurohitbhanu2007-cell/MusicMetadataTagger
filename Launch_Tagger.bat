@echo off
setlocal enabledelayedexpansion
title Music Metadata Tagger

:: Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in PATH! Please ensure Python is installed.
    pause
    exit /b 1
)

:: If a directory is dragged and dropped onto this batch file
if not "%~1"=="" (
    set "TARGET_DIR=%~1"
    goto RUN_DRAG_DROP
)

:MENU
cls
echo =======================================================
echo               MUSIC METADATA TAGGER
echo =======================================================
echo.
echo   [1] Tag English Music   (C:\Users\rajpu\Music\EnglishMusic)
echo   [2] Tag Hindi Music     (C:\Users\rajpu\Music\HindiMusic)
echo   [3] Tag Custom Folder   (Enter path or drag-and-drop)
echo   [4] Dry-Run Preview     (Scan without writing changes)
echo   [5] Overwrite / Refresh (Re-tag entire folder online)
echo   [6] Clean Duplicates    (Find & delete duplicate copies)
echo   [7] Exit
echo =======================================================
set /p "CHOICE=Enter your choice [1-7]: "

if "%CHOICE%"=="1" goto RUN_ENGLISH
if "%CHOICE%"=="2" goto RUN_HINDI
if "%CHOICE%"=="3" goto PROMPT_CUSTOM
if "%CHOICE%"=="4" goto MENU_DRYRUN
if "%CHOICE%"=="5" goto MENU_OVERWRITE
if "%CHOICE%"=="6" goto MENU_DEDUP
if "%CHOICE%"=="7" exit /b 0
echo Invalid choice, please try again.
ping 127.0.0.1 -n 2 >nul
goto MENU

:RUN_ENGLISH
echo.
echo Processing English Music...
python "%~dp0tagger.py" "C:\Users\rajpu\Music\EnglishMusic"
goto FINISH

:RUN_HINDI
echo.
echo Processing Hindi Music...
python "%~dp0tagger.py" "C:\Users\rajpu\Music\HindiMusic"
goto FINISH

:MENU_DRYRUN
cls
echo =======================================================
echo                 DRY-RUN PREVIEW MODE
echo =======================================================
echo   [1] Preview English Music
echo   [2] Preview Hindi Music
echo   [3] Preview Custom Folder
echo   [4] Back to Main Menu
echo =======================================================
set /p "DRY_CHOICE=Enter choice [1-4]: "
if "%DRY_CHOICE%"=="1" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\EnglishMusic" --dry-run
    goto FINISH
)
if "%DRY_CHOICE%"=="2" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\HindiMusic" --dry-run
    goto FINISH
)
if "%DRY_CHOICE%"=="3" (
    set /p "CUST=Enter folder: "
    set "CUST=!CUST:"=!"
    if "!CUST:~-1!"=="\" set "CUST=!CUST:~0,-1!"
    python "%~dp0tagger.py" "!CUST!" --dry-run
    goto FINISH
)
goto MENU

:MENU_OVERWRITE
cls
echo =======================================================
echo              OVERWRITE & REFRESH MODE
echo =======================================================
echo   [WARNING] This will overwrite existing metadata with online tags.
echo   [1] Overwrite English Music
echo   [2] Overwrite Hindi Music
echo   [3] Overwrite Custom Folder
echo   [4] Back to Main Menu
echo =======================================================
set /p "OW_CHOICE=Enter choice [1-4]: "
if "%OW_CHOICE%"=="1" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\EnglishMusic" --overwrite
    goto FINISH
)
if "%OW_CHOICE%"=="2" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\HindiMusic" --overwrite
    goto FINISH
)
if "%OW_CHOICE%"=="3" (
    set /p "CUST=Enter folder: "
    set "CUST=!CUST:"=!"
    if "!CUST:~-1!"=="\" set "CUST=!CUST:~0,-1!"
    python "%~dp0tagger.py" "!CUST!" --overwrite
    goto FINISH
)
goto MENU

:MENU_DEDUP
cls
echo =======================================================
echo             CLEAN DUPLICATE MUSIC FILES
echo =======================================================
echo   [1] Clean Duplicates in English Music
echo   [2] Clean Duplicates in Hindi Music
echo   [3] Clean Duplicates in Custom Folder
echo   [4] Back to Main Menu
echo =======================================================
set /p "DEDUP_CHOICE=Enter choice [1-4]: "
if "%DEDUP_CHOICE%"=="1" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\EnglishMusic" --dedup
    goto FINISH
)
if "%DEDUP_CHOICE%"=="2" (
    python "%~dp0tagger.py" "C:\Users\rajpu\Music\HindiMusic" --dedup
    goto FINISH
)
if "%DEDUP_CHOICE%"=="3" (
    set /p "CUST=Enter folder: "
    set "CUST=!CUST:"=!"
    if "!CUST:~-1!"=="\" set "CUST=!CUST:~0,-1!"
    python "%~dp0tagger.py" "!CUST!" --dedup
    goto FINISH
)
goto MENU

:PROMPT_CUSTOM
echo.
set /p "TARGET_DIR=Enter or drag-and-drop the music folder path: "
set "TARGET_DIR=%TARGET_DIR:"=%"
:RUN_DRAG_DROP
if "%TARGET_DIR:~-1%"=="\" set "TARGET_DIR=%TARGET_DIR:~0,-1%"
if not exist "%TARGET_DIR%" (
    echo [ERROR] Directory "%TARGET_DIR%" does not exist!
    pause
    goto MENU
)
echo.
echo Processing custom directory: "%TARGET_DIR%"
python "%~dp0tagger.py" "%TARGET_DIR%"
goto FINISH

:FINISH
echo.
echo =======================================================
echo Process complete.
echo =======================================================
echo Press any key to return to menu...
pause >nul
goto MENU
