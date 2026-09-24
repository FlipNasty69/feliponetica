@echo off
set "CWEBP=C:\Users\demon\OneDrive\Desktop\libwebp-1.6.0-windows-x64\bin\cwebp.exe"

for %%F in (*.jpg *.jpeg *.png) do (
    "%CWEBP%" -q 80 "%%F" -o "%%~nF.webp"
)

echo.
echo DONE!
pause