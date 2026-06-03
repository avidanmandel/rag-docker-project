# Prepare clean submission ZIP with manifest and SHA-256.
param(
    [switch]$PreCleanup
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $Root "dist"
$suffix = if ($PreCleanup) { "-pre-cleanup" } else { "" }
$ZipPath = Join-Path $OutDir "Avidan_RAG_Docker_Project-submission$suffix.zip"
$ManifestPath = Join-Path $OutDir "Avidan_RAG_Docker_Project-submission$suffix.manifest.txt"
$ShaPath = Join-Path $OutDir "Avidan_RAG_Docker_Project-submission$suffix.sha256.txt"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$excludePatterns = @(
    ".git", ".env", ".aws", "artifacts", "runtime", ".venv", "venv",
    "__pycache__", ".pytest_cache", "home-preview-", "screenshoot",
    "submission_evidence\archive", "docs\archive", "dist",
    "static\images\design-reference.png",
    "static\images\home-dashboard-panel.png", "static\images\player-home.png",
    "static\images\sir-alex-home.png"
)
$excludeFiles = @("*.pem", "*.key", "*.log", "chat.db", "*.db", "*.bak")
$excludeZipSelf = "dist\Avidan_RAG_Docker_Project-submission"

$files = Get-ChildItem -Path $Root -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($Root.Length + 1)
    if ($rel.StartsWith($excludeZipSelf)) { return $false }
    foreach ($pat in $excludePatterns) {
        if ($rel -like "*$pat*") { return $false }
    }
    foreach ($pat in $excludeFiles) {
        if ($_.Name -like $pat) { return $false }
    }
    if ($rel -match 'scripts\\(audit_|deploy_session_docs_v[3-7]|validate_candidate|validate_prod|validate_public|candidate_|cutover_session_docs_v[34])') { return $false }
    if ($rel -match '\\rollback\\') { return $false }
    if ($rel -eq 'tests\escape.txt') { return $false }
    return $true
} | Sort-Object FullName

$relPaths = $files | ForEach-Object { $_.FullName.Substring($Root.Length + 1).Replace("\", "/") }
$relPaths | Set-Content -Path $ManifestPath -Encoding utf8

Compress-Archive -Path ($files | ForEach-Object { $_.FullName }) -DestinationPath $ZipPath -Force

$hash = Get-FileHash -Path $ZipPath -Algorithm SHA256
"$($hash.Hash)  $(Split-Path -Leaf $ZipPath)" | Set-Content -Path $ShaPath -Encoding utf8

Write-Host "submission_zip=$ZipPath"
Write-Host "manifest=$ManifestPath"
Write-Host "sha256=$ShaPath"
Write-Host "file_count=$($files.Count)"
Write-Host "sha256_hash=$($hash.Hash)"
Get-Item $ZipPath | Select-Object Length, FullName
