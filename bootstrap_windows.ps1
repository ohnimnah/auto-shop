$ErrorActionPreference = 'Stop'

Set-Location -Path $PSScriptRoot
Write-Host ''
Write-Host '=============================================='
Write-Host ' auto_shop Windows 환경 자동 설치 시작'
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
    Write-Host 'Python이 설치되어 있지 않아 자동 설치를 시도합니다...'

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    }
    else {
        Write-Host 'winget을 찾지 못했습니다. Microsoft Store 또는 python.org에서 Python 설치 후 다시 실행해주세요.' -ForegroundColor Yellow
        exit 1
    }

    $pythonCmd = Get-PythonCommand
    if (-not $pythonCmd) {
        Write-Host 'Python 명령을 찾지 못했습니다. 터미널을 재시작한 뒤 다시 실행해주세요.' -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Test-Path '.venv')) {
    Write-Host '.venv 가상환경 생성 중...'
    if ($pythonCmd -eq 'py -3') {
        py -3 -m venv .venv
    }
    else {
        python -m venv .venv
    }
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host '가상환경 Python 실행 파일을 찾지 못했습니다.' -ForegroundColor Red
    exit 1
}

Write-Host 'pip 업그레이드 및 패키지 설치 중...'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ''
Write-Host '완료: Python/패키지 설치가 끝났습니다.' -ForegroundColor Green
Write-Host '다음부터는 run.bat에서 자동화를 실행하세요.'
