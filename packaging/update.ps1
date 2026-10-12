param([string]$TargetDirectory, [switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
function HashFile([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function SafePath([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)' -or $Relative -match '^(?i:data)([\\/]|$)') { throw 'Unsafe update path.' }
    $path = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe update path.' }
    $cursor = $path
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Symbolic links/junctions cannot be updated.' }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }; $cursor = $parent
    }
    return $path
}
$backup = $null; $stage = $null; $modified = [Collections.Generic.List[string]]::new(); $old = @{}
try {
    if (-not $TargetDirectory) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Select the existing folder containing LocalMediaLibrary.exe.'
        $dialog.ShowNewFolderButton = $false
        if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { exit 0 }
        $TargetDirectory = $dialog.SelectedPath
    }
    $target = [IO.Path]::GetFullPath($TargetDirectory)
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $exe = SafePath $target 'LocalMediaLibrary.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'LocalMediaLibrary.exe was not found in this folder.' }
    if (Get-Process -Name LocalMediaLibrary -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }) { throw 'Close Local Media Library before updating.' }
    # Check the supported old application, never DB/cache/media files.
    $already = $true
    foreach ($entry in $manifest.after) {
        $file = SafePath $target $entry.path
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (HashFile $file) -ne $entry.sha256) { $already = $false; break }
    }
    if ($already) { Write-Host 'This update is already applied.'; exit 0 }
    $versions = @($manifest)
    if ($manifest.PSObject.Properties.Name -contains 'variants') { $versions = @($manifest.variants) }
    $selected = $null
    foreach ($version in $versions) {
        $matches = $true
        foreach ($entry in $version.before) {
            $file = SafePath $target $entry.path
            if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (HashFile $file) -ne $entry.sha256) { $matches = $false; break }
        }
        if ($matches) { $selected = $version; break }
    }
    if (-not $selected) { throw 'Unsupported or modified old version. No application files were changed.' }
    $manifest.before = $selected.before
    $manifest.changed = $selected.changed
    foreach ($entry in $manifest.changed) {
        $old[$entry.path] = $entry.old_sha256
        $file = SafePath $target $entry.path
        if (-not $entry.old_sha256 -and (Test-Path -LiteralPath $file)) { throw ('Unexpected existing application file: ' + $entry.path) }
        if ($entry.new_sha256) {
            $payload = SafePath (Join-Path $PSScriptRoot 'payload') $entry.path
            if ((HashFile $payload) -ne $entry.new_sha256) { throw ('Damaged update file: ' + $entry.path) }
        }
    }
    $suffix = Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
    $backup = Join-Path $target ('_update-backup-' + $suffix)
    $stage = Join-Path $target ('_update-stage-' + $suffix)
    New-Item -ItemType Directory -Path $backup | Out-Null
    New-Item -ItemType Directory -Path $stage | Out-Null
    # Back up originals and stage all replacements before modifying the app.
    foreach ($entry in $manifest.changed) {
        if ($entry.old_sha256) {
            $saved = SafePath $backup $entry.path
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $saved) | Out-Null
            Copy-Item -LiteralPath (SafePath $target $entry.path) -Destination $saved
            if ((HashFile $saved) -ne $entry.old_sha256) { throw 'Backup verification failed.' }
        }
        if ($entry.new_sha256) {
            $staged = SafePath $stage $entry.path
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $staged) | Out-Null
            Copy-Item -LiteralPath (SafePath (Join-Path $PSScriptRoot 'payload') $entry.path) -Destination $staged
        }
    }
    foreach ($entry in $manifest.changed) {
        $file = SafePath $target $entry.path
        $modified.Add($entry.path)
        if ($entry.new_sha256) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
            Copy-Item -LiteralPath (SafePath $stage $entry.path) -Destination $file -Force
        } elseif (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
    }
    foreach ($entry in $manifest.after) {
        if ((HashFile (SafePath $target $entry.path)) -ne $entry.sha256) { throw ('Final verification failed: ' + $entry.path) }
    }
    Remove-Item -LiteralPath $stage -Recurse -Force; $stage = $null
    Write-Host 'Update complete. DB, settings, cache and original media were preserved.'
    Write-Host ('Application-file backup: ' + $backup)
    if (-not $NonInteractive) { Read-Host 'Press Enter to close' | Out-Null }
    exit 0
} catch {
    $message = $_.Exception.Message
    $rollbackFailed = $false
    foreach ($relative in $modified) {
        try {
            $file = SafePath $target $relative
            if ($old[$relative]) { Copy-Item -LiteralPath (SafePath $backup $relative) -Destination $file -Force }
            elseif (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
        } catch { $rollbackFailed = $true }
    }
    if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host ('Update stopped: ' + $message)
    if ($rollbackFailed) { Write-Host ('Some application files could not be restored. Keep the app closed and use backup: ' + $backup) }
    elseif ($modified.Count) { Write-Host 'Changed application files were restored.' }
    if (-not $NonInteractive) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
