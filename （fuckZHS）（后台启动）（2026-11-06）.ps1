# fuckZHS 后台隐藏启动器
# 作用：无窗口启动 main.py，输出写入 logs\stdout.log，不打扰前台

$ErrorActionPreference = 'SilentlyContinue'

$proj   = 'C:\Users\JD\Desktop\fuckZHS'
$py     = Join-Path $proj '.venv\Scripts\python.exe'
$outLog = Join-Path $proj 'logs\stdout.log'
$errLog = Join-Path $proj 'logs\stderr.log'

Set-Location $proj

Start-Process -FilePath $py `
    -ArgumentList 'main.py' `
    -WorkingDirectory $proj `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog
