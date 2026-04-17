$ErrorActionPreference = 'Stop'

Set-Location -Path $PSScriptRoot
Write-Host ''
Write-Host '=============================================='
Write-Host ' auto_shop Windows bootstrap start'
Write-Host '=============================================='
Write-Host ''

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return 'py -3'
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }

    return $null
}

$pythonCmd = Get-PythonCommand

if (-not $pythonCmd) {
    Write-Host 'Python is not installed. Trying automatic install...'

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    }
    else {
        Write-Host 'winget was not found. Install Python from Microsoft Store or python.org, then run again.' -ForegroundColor Yellow
        exit 1
    }

    $pythonCmd = Get-PythonCommand
    if (-not $pythonCmd) {
        Write-Host 'Python command still not found. Reopen terminal and run again.' -ForegroundColor Yellow
        exit 1
    }
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function New-Venv {
    Write-Host 'Creating virtual environment (.venv)...'
    if ($pythonCmd -eq 'py -3') {
        py -3 -m venv .venv
    }
    else {
        python -m venv .venv
    }
}

if (-not (Test-Path '.venv')) {
    New-Venv
}

if (-not (Test-Path $venvPython)) {
    Write-Host 'Broken virtual environment detected. Recreating .venv...' -ForegroundColor Yellow
    if (Test-Path '.venv') {
        Remove-Item -Recurse -Force '.venv'
    }
    New-Venv
}

if (-not (Test-Path $venvPython)) {
    Write-Host 'Virtual environment python executable was not found after recreation.' -ForegroundColor Red
    exit 1
}

Write-Host 'Installing required packages...'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ''
Write-Host 'Done: Python/package bootstrap completed.' -ForegroundColor Green
Write-Host 'Now choose an option from run.bat menu.'
