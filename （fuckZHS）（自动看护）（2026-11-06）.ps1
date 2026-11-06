# fuckZHS 自动看护
# 每 10 分钟跑一次：进程死了自动重启、卡住了自动重启、异常信号写进 watchdog.log

$ErrorActionPreference = 'SilentlyContinue'

$proj    = 'C:\Users\JD\Desktop\fuckZHS'
$py      = Join-Path $proj '.venv\Scripts\python.exe'
$wdLog   = Join-Path $proj 'logs\watchdog.log'
$errLog  = Join-Path $proj 'logs\error.log'
$infoLog = Join-Path $proj 'logs\info.log'
$outLog  = Join-Path $proj 'logs\stdout.log'
$errOut  = Join-Path $proj 'logs\stderr.log'

function Write-Wd($msg) {
    $line = (Get-Date -Format 'MM-dd HH:mm:ss') + '  ' + $msg
    Add-Content -LiteralPath $wdLog -Value $line -Encoding UTF8
}

function Get-ZhsProc {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*fuckZHS*' }
}

function Test-Net {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $ar = $c.BeginConnect('studyservice-api.zhihuishu.com', 443, $null, $null)
        $ok = $ar.AsyncWaitHandle.WaitOne(4000)
        $c.Close()
        return $ok
    } catch {
        return $false
    }
}

function Start-Zhs {
    Set-Location $proj
    Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory $proj `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errOut
}

$procs = @(Get-ZhsProc)

if ($procs.Count -eq 0) {
    if (-not (Test-Net)) {
        Write-Wd '进程已退出，但网络不通 -> 本轮跳过，等网络恢复'
        exit
    }
    $today = Get-Date -Format 'MM-dd'
    $restarts = @()
    if (Test-Path $wdLog) {
        $restarts = @(Get-Content -LiteralPath $wdLog | Where-Object { $_ -like "*$today*" -and $_ -like '*自动重启*' })
    }
    if ($restarts.Count -ge 3) {
        Write-Wd '今日已自动重启 3 次，暂停自动重启，需人工检查'
        exit
    }
    Start-Zhs
    Write-Wd '检测到进程不在运行 -> 已自动重启'
    exit
}

$tail = @(Get-Content -LiteralPath $errLog -Tail 60)
$hits = @()
if ($tail -match 'captcha required')      { $hits += 'CAPTCHA' }
if ($tail -match '疑是多窗口观看')         { $hits += 'MULTI_WINDOW' }
if ($tail -match 'getaddrinfo failed')    { $hits += 'DNS' }
if ($hits.Count -gt 0) { Write-Wd ('异常信号: ' + ($hits -join ',')) }

$idle = 0
if (Test-Path $infoLog) {
    $idle = [math]::Round(((Get-Date) - (Get-Item $infoLog).LastWriteTime).TotalMinutes)
}

if ($idle -ge 90) {
    Write-Wd ("日志已 $idle 分钟无更新，判定卡住 -> 重启进程")
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Seconds 3
    Start-Zhs
    Write-Wd '已自动重启（停滞恢复）'
} else {
    $pid0 = $procs[0].ProcessId
    Write-Wd ("正常 pid=$pid0 日志空闲=$idle 分钟")
}
