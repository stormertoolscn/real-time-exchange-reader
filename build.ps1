# 打包「汇率小宝 v2」为独立 exe（Win10/11）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> 安装依赖..." -ForegroundColor Cyan
python -m pip install -r requirements.txt -q

Write-Host "==> PyInstaller 打包..." -ForegroundColor Cyan
python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onefile `
  --name "HuilvXiaobao2" `
  --hidden-import=bs4 `
  --hidden-import=PIL `
  --hidden-import=pyautogui `
  --hidden-import=pyperclip `
  --hidden-import=requests `
  --collect-all=webview `
  --collect-all=pyautogui `
  --add-data "ui;ui" `
  --add-data "core;core" `
  app.py

if (Test-Path "dist\HuilvXiaobao2.exe") {
  Copy-Item "dist\HuilvXiaobao2.exe" "dist\汇率小宝 v2.exe" -Force
  Copy-Item "dist\HuilvXiaobao2.exe" "dist\汇率小宝 v2.0.1.exe" -Force
  $size = (Get-Item "dist\HuilvXiaobao2.exe").Length / 1MB
  Write-Host ("==> 完成: dist\HuilvXiaobao2.exe / dist\汇率小宝 v2.0.1.exe ({0:N1} MB)" -f $size) -ForegroundColor Green
} else {
  Write-Host "==> 打包失败" -ForegroundColor Red
  exit 1
}
