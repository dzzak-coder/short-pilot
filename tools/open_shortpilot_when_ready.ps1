$ErrorActionPreference = 'SilentlyContinue'

$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', 'start "" "http://127.0.0.1:8000/"') -WindowStyle Hidden
            exit 0
        }
    } catch {
        # The Flask server is still starting.
    }
    Start-Sleep -Milliseconds 500
}

exit 1
