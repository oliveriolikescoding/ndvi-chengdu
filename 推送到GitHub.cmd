@echo off
cd /d "%~dp0"

echo.
echo ==========================================================
echo   ndvi-chengdu  -  push figures / data / docs to GitHub
echo ==========================================================
echo   repo: https://github.com/oliveriolikescoding/ndvi-chengdu
echo.
echo   Code and docs were already pushed by the agent.
echo   This step uploads the binary deliverables
echo   (PNG / PDF / SVG) plus the local git history.
echo.
echo   On the first run a browser window will ask you to sign
echo   in to GitHub. Use the account "oliveriolikescoding".
echo   It is remembered afterwards.
echo.

git config --local credential.helper manager
git add -A
git commit -m "v1.1 local changes" >nul 2>&1

powershell -NoProfile -Command "if (Test-NetConnection 127.0.0.1 -Port 7897 -WarningAction SilentlyContinue -InformationLevel Quiet) { exit 0 } else { exit 1 }"
if errorlevel 1 goto direct

:proxy
echo [net] using local proxy 127.0.0.1:7897
git -c http.proxy=http://127.0.0.1:7897 push -u origin main --force
goto check

:direct
echo [net] no proxy on 7897 found, trying direct connection
git push -u origin main --force

:check
if errorlevel 1 goto failed

echo.
echo ----------------------------------------------------------
echo   OK. Open the repo and check the figures:
echo   https://github.com/oliveriolikescoding/ndvi-chengdu
echo ----------------------------------------------------------
pause
exit /b 0

:failed
echo.
echo ----------------------------------------------------------
echo   FAILED. Usual causes:
echo   1) sign-in cancelled  -^> run this file again, click Authorize
echo   2) no network         -^> check that the proxy on 7897 is on
echo   3) wrong account      -^> must be oliveriolikescoding
echo ----------------------------------------------------------
pause
exit /b 1
