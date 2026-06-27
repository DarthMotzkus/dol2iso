# Builda o dol2iso.exe standalone (onefile, sem console) com PyInstaller.
# Requer: Python + pip install pyinstaller pillow
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

py -m PyInstaller --noconfirm --onefile --windowed --name dol2iso `
    --icon "assets\dolphin.ico" `
    --add-data "assets\gbi.hdr;assets" `
    --add-data "assets\default_banner.png;assets" `
    --add-data "assets\dolphin.ico;assets" `
    --collect-submodules PIL `
    dol2iso_gui.py

Write-Host ""
Write-Host ">> EXE: $PSScriptRoot\dist\dol2iso.exe"
