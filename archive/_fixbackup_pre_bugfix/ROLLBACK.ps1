# ОТКАТ всех фиксов (restore из бэкапа, выполняется из корня проекта):
#   pwsh -File _fixbackup_pre_bugfix/ROLLBACK.ps1
$root = Split-Path $PSScriptRoot -Parent
$map = @{
  "confirm_gate.py" = "confirm_gate.py"; "advanced_gate_scanner.py" = "advanced_gate_scanner.py"
  "gate_client.py" = "gate_client.py"; "store_gate.py" = "store_gate.py"
  "db.py" = "bot\db.py"; "main.py" = "bot\main.py"
  "piconfirm.py" = "bot\gates\piconfirm.py"; "setupwoo.py" = "bot\gates\setupwoo.py"
}
foreach ($k in $map.Keys) {
  Copy-Item (Join-Path $PSScriptRoot $k) (Join-Path $root $map[$k]) -Force
  Write-Host "restored $($map[$k])"
}
Write-Host "done — все 8 файлов возвращены к пре-фикс состоянию"
