param(
    [switch]$Reload,
    [ValidateRange(1, 65535)]
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath "config.yaml" -PathType Leaf)) {
        throw "Copy config.example.yaml to config.yaml before starting Forge."
    }

    $pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $pythonArgs = @()
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($launcher) {
            $pythonExe = $launcher.Source
            $pythonArgs = @("-3")
        } else {
            $pythonExe = (Get-Command python -CommandType Application | Select-Object -First 1).Source
        }
    }

    $serverArgs = @("-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "$Port")
    if ($Reload) { $serverArgs += "--reload" }
    & $pythonExe @pythonArgs @serverArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
