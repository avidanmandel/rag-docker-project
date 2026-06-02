# Prepare clean submission ZIP (PowerShell fallback for Windows dev hosts).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $Root "dist"
$ZipPath = Join-Path $OutDir "Avidan_RAG_Docker_Project-submission.zip"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$excludePatterns = @(
    ".git", ".env", ".aws", "artifacts\logs", "runtime", ".venv", "venv",
    "__pycache__", "home-preview-", "dist\Avidan_RAG_Docker_Project-submission.zip"
)
$excludeFiles = @("*.pem", "*.key", "*.log", "chat.db", "*.db")

$files = Get-ChildItem -Path $Root -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($Root.Length + 1)
    foreach ($pat in $excludePatterns) {
        if ($rel -like "*$pat*") { return $false }
    }
    foreach ($pat in $excludeFiles) {
        if ($_.Name -like $pat) { return $false }
    }
    if ($rel -match 'scripts\\(audit_|deploy_session_docs_v[3-7]|validate_candidate|validate_prod|validate_public|candidate_|cutover_)') { return $false }
    return $true
}

Compress-Archive -Path ($files | ForEach-Object { $_.FullName }) -DestinationPath $ZipPath -Force
Write-Host "submission_zip=$ZipPath"
Write-Host "file_count=$($files.Count)"
Get-Item $ZipPath | Select-Object Length, FullName
