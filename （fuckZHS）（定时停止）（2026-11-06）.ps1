# 21:00 定时停止刷课
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*fuckZHS*main.py*' }

foreach ($p in $procs) {
    Stop-Process -Id $p.ProcessId -Force
}

$line = (Get-Date -Format 'MM-dd HH:mm:ss') + '  已到达 21:00 定时停止，关闭刷课进程'
Add-Content -LiteralPath 'C:\Users\JD\Desktop\fuckZHS\logs\watchdog.log' -Value $line -Encoding UTF8
