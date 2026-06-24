$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*manage.py runserver 127.0.0.1:8000*" }

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force
}

Write-Host "Servidor local encerrado."
