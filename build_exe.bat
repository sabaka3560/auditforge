@echo off
echo Building AuditForge...
pyinstaller --clean --noconfirm ^
  --onedir --windowed ^
  --name AuditForge ^
  --add-data "static;static" ^
  --add-data "ideals;ideals" ^
  --collect-all webview ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import engineio.async_drivers.threading ^
  main.py

echo.
echo Done. Distributable: dist\AuditForge\
pause
