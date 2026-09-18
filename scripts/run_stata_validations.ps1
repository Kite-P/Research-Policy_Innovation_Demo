param(
    [ValidateSet("00", "01", "02", "03", "04", "05", "06", "07", "all")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$stata = $env:STATA_EXE
if ([string]::IsNullOrWhiteSpace($stata)) {
    $stata = [Environment]::GetEnvironmentVariable("STATA_EXE", "User")
}
if ([string]::IsNullOrWhiteSpace($stata)) {
    $stata = [Environment]::GetEnvironmentVariable("STATA_EXE", "Machine")
}
if ([string]::IsNullOrWhiteSpace($stata)) {
    $candidate = Get-Command StataMP-64.exe, StataMP.exe, stata-mp.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { $stata = $candidate.Source }
}
if ([string]::IsNullOrWhiteSpace($stata) -or -not (Test-Path -LiteralPath $stata)) {
    throw "Stata executable unavailable; set STATA_EXE."
}

$names = @{
    "00" = "00_environment_check.do"
    "01" = "01_validate_clean_financials.do"
    "02" = "02_validate_clean_profile.do"
    "03" = "03_validate_clean_patents.do"
    "04" = "04_validate_research_panel.do"
    "05" = "05_validate_research_variables.do"
    "06" = "06_first_stage_analysis.do"
    "07" = "07_validate_policy_panel.do"
}
$targets = if ($Target -eq "all") { @("00", "01", "02", "03", "04", "05", "06", "07") } else { @($Target) }
foreach ($number in $targets) {
    $doFile = "stata/$($names[$number])"
    $process = Start-Process -FilePath $stata -ArgumentList @("/e", "do", $doFile) -WorkingDirectory (Get-Location) -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0) { throw "Stata validation $number returned exit code $($process.ExitCode)." }
    $autoLog = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetFileName($doFile), ".log")
    if (Test-Path -LiteralPath $autoLog) {
        Move-Item -LiteralPath $autoLog -Destination ("logs/" + $autoLog.Replace(".log", ".batch.log")) -Force
    }
    Write-Output ("STATA_VALIDATION_{0}_PASS" -f $number)
}
Write-Output "STATA_VALIDATIONS_PASS"
