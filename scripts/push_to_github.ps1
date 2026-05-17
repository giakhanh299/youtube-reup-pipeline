param(
  [string]$RepoName = "youtube-reup-pipeline",
  [string]$GitUserName = "Nguyen Huu Gia Khanh",
  [string]$GitUserEmail = "your-email@example.com"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Reup Pipeline: GitHub Push Script ===" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "Git chưa được cài hoặc chưa có trong PATH. Cài Git for Windows trước."
}

if (-not (Test-Path "pipeline.py")) {
  throw "Hãy chạy script này bên trong thư mục project có file pipeline.py"
}

git config --global user.name "$GitUserName"
git config --global user.email "$GitUserEmail"

if (-not (Test-Path ".git")) {
  git init
}

git branch -M main

git add .
git commit -m "phase 0: initial sheet controlled reup pipeline" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Không có thay đổi mới để commit hoặc commit đã tồn tại." -ForegroundColor Yellow
}

Write-Host "\nTạo repo GitHub bằng GitHub CLI nếu có..." -ForegroundColor Cyan
if (Get-Command gh -ErrorAction SilentlyContinue) {
  gh repo create $RepoName --private --source=. --remote=origin --push
} else {
  Write-Host "Bạn chưa có GitHub CLI. Tạo repo rỗng trên GitHub trước, rồi chạy:" -ForegroundColor Yellow
  Write-Host "git remote add origin https://github.com/YOUR_USERNAME/$RepoName.git"
  Write-Host "git push -u origin main"
}

Write-Host "\nTạo phase branches..." -ForegroundColor Cyan
$branches = @(
  "phase-1-sheet-control",
  "phase-2-input-matching",
  "phase-3-voice-engine",
  "phase-4-render-engine",
  "phase-5-multi-channel-scale",
  "phase-6-upload-handoff",
  "phase-7-codex-cleanup"
)

foreach ($b in $branches) {
  git checkout -B $b main
  git push -u origin $b 2>$null
}

git checkout main
Write-Host "\nXong. Mở Codex và connect repo này." -ForegroundColor Green
