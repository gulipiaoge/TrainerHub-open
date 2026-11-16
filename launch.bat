@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TrainerHub - 修改器管理器
echo.
echo   TrainerHub 正在启动...
echo   所有数据仅保存在本目录 data\ 下
echo.
"%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
if errorlevel 1 (
  echo.
  echo [提示] 若窗口未出现，请检查 WebView2 运行时是否安装。
  pause
)
exit
