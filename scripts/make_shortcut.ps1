# Creates "CTF Copilot" shortcuts on the Desktop and Start Menu that launch
# the app with pythonw.exe (no console window). Re-run any time; it overwrites.
#
#   powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$launch = Join-Path $repo "launch.pyw"

# Find pythonw.exe next to the python that can import the package.
$pythonw = $null
foreach ($cmd in @("python", "py")) {
    $exe = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
    if ($exe) {
        $cand = Join-Path (Split-Path $exe) "pythonw.exe"
        if (Test-Path $cand) { $pythonw = $cand; break }
    }
}
if (-not $pythonw) {
    $cand = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
    if ($cand) { $pythonw = $cand }
}
if (-not $pythonw) { throw "pythonw.exe not found - is Python installed?" }

$ws = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
)
foreach ($dir in $targets) {
    $lnkPath = Join-Path $dir "CTF Copilot.lnk"
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '"' + $launch + '"'
    $lnk.WorkingDirectory = $repo
    $lnk.IconLocation = "$pythonw,0"
    $lnk.Description = "CTF Copilot - autonomous CTF assistant"
    $lnk.Save()
    Write-Output "Created: $lnkPath"
}
Write-Output "Done. Double-click 'CTF Copilot' on your Desktop to launch."
