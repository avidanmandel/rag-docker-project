# Prepare clean submission ZIP — delegates to canonical Python packager with validation.
param(
    [switch]$PreCleanup
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Args = @("scripts/prepare_submission_zip.py")
if ($PreCleanup) { $Args += "--pre-cleanup" }
& python @Args
exit $LASTEXITCODE
