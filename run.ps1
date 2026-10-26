param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $projectRoot "backend\requirements.txt"

if (-not (Test-Path $venvPython)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -m venv (Join-Path $projectRoot ".venv")
    } else {
        $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $pythonLauncher) {
            throw "Python 3.10 or newer is required. Install Python and make sure 'python' or 'py' is on PATH."
        }
        & $pythonLauncher.Source -3 -m venv (Join-Path $projectRoot ".venv")
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install backend dependencies."
}

Push-Location (Join-Path $projectRoot "backend")
try {
    Write-Host "NexlyticX is starting at http://127.0.0.1:$Port"
    & $venvPython -m uvicorn main:app --reload --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "NexlyticX stopped with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
