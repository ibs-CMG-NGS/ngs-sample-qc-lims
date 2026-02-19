# NGS Sample QC LIMS 실행 스크립트
# PowerShell에서 실행: .\run.ps1

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  NGS Sample QC LIMS - Starting..." -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# Conda 환경 확인
$envName = "ngs-sample-qc-lims"
$envList = conda env list 2>&1 | Select-String -Pattern $envName

if ($envList) {
    Write-Host "[OK] Conda environment '$envName' found" -ForegroundColor Green
    Write-Host ""
    Write-Host "Starting application with conda run..." -ForegroundColor Yellow
    Write-Host ""
    
    # Conda 환경에서 실행
    conda run -n $envName python main.py
    
} else {
    Write-Host "[ERROR] Conda environment '$envName' not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please create the environment first:" -ForegroundColor Yellow
    Write-Host "  conda env create -f environment.yml" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}
