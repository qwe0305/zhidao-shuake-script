# fuckZHS 后台隐藏启动器
# 作用：无窗口启动 main.py，输出写入 logs\stdout.log，不打扰前台

$ErrorActionPreference = 'SilentlyContinue'

$proj   = 'C:\Users\JD\Desktop\fuckZHS'
$py     = Join-Path $proj '.venv\Scripts\python.exe'
$outLog = Join-Path $proj 'logs\stdout.log'
$errLog = Join-Path $proj 'logs\stderr.log'
$qr     = Join-Path $proj 'qr'

# 智慧树是国内站，走 Clash 代理会卡住/证书报错，强制直连
$env:HTTP_PROXY = ''
$env:HTTPS_PROXY = ''
$env:http_proxy = ''
$env:https_proxy = ''
$env:ALL_PROXY = ''

Set-Location $proj

Start-Process -FilePath $py `
    -ArgumentList @('-u', 'main.py', '-s', '1.25', '--image_path', "`"$qr`"") `
    -WorkingDirectory $proj `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog
