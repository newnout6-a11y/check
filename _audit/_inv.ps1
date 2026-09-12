
$ErrorActionPreference='Continue'
$root='C:\Users\Redmi\Downloads\pusto'
Write-Output "=== TOP LEVEL ==="
Get-ChildItem -Force $root | Select-Object Mode,Name,Length | Format-Table -AutoSize | Out-String -Width 200
Write-Output "=== _audit ==="
Get-ChildItem -Force "$root\_audit" -ErrorAction SilentlyContinue | Select-Object Name,Length | Format-Table -AutoSize | Out-String -Width 200
Write-Output "=== MD FILES (recursive) ==="
Get-ChildItem -Recurse -Force -File $root -Include *.md -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\(\.git|node_modules|\.venv|venv|site-packages|__pycache__)\\' } | ForEach-Object { $rel = $_.FullName.Substring($root.Length+1); $n = (Get-Content $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines; "$rel :: $n lines" } | Sort-Object
Write-Output "=== DIRS (depth 2) ==="
Get-ChildItem -Recurse -Force -Directory $root -Depth 2 -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\(\.git|node_modules|__pycache__|\.venv)\\' } | ForEach-Object { $_.FullName.Substring($root.Length+1) } | Sort-Object
