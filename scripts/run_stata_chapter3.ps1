param(
    [ValidateSet("08", "09", "10", "all")]
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
    if ($candidate) {
        $stata = $candidate.Source
    }
}
if ([string]::IsNullOrWhiteSpace($stata) -or -not (Test-Path -LiteralPath $stata)) {
    throw "Stata executable unavailable; set STATA_EXE."
}
Write-Output "Stata executable verified"

$targets = if ($Target -eq "all") { @("08", "09", "10") } else { @($Target) }
foreach ($number in $targets) {
    $doFile = "stata/$number" + $(switch ($number) {
        "08" { "_policy_baseline.do" }
        "09" { "_policy_timing_robustness.do" }
        "10" { "_policy_measurement_robustness.do" }
    })
    $process = Start-Process -FilePath $stata -ArgumentList @("/e", "do", $doFile) -WorkingDirectory (Get-Location) -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0) {
        throw "Stata target $number returned exit code $($process.ExitCode)."
    }
    $autoLog = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetFileName($doFile), ".log")
    if (Test-Path -LiteralPath $autoLog) {
        Move-Item -LiteralPath $autoLog -Destination ("logs/" + $autoLog.Replace(".log", ".batch.log")) -Force
    }
    $log = "logs/$number" + $(switch ($number) {
        "08" { "_policy_baseline.log" }
        "09" { "_policy_timing_robustness.log" }
        "10" { "_policy_measurement_robustness.log" }
    })
    if (-not (Test-Path -LiteralPath $log)) {
        throw "Missing log for target $number."
    }
    $sentinel = "CHAPTER3_" + $number + "_OK"
    if (-not (Select-String -LiteralPath $log -Pattern $sentinel -Quiet)) {
        throw "Sentinel $sentinel not found."
    }
    Write-Output ("CHAPTER3_{0}_PASS" -f $number)
}
Write-Output "CHAPTER3_RUNNER_PASS"
