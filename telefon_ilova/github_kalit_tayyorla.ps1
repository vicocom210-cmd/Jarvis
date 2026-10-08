# GitHub Actions APK'ni yangi maxfiy kalit bilan imzolashi uchun 2 ta Secret kerak.
# Ishga tushirish: PowerShell'da  .\telefon_ilova\github_kalit_tayyorla.ps1
# Skript qiymatlarni ekranga chiqarmaydi - navbat bilan almashish buferiga (Ctrl+V) nusxalaydi.
$papka = $PSScriptRoot
$sozlama = @{}
Get-Content (Join-Path $papka 'keystore.properties') | Where-Object { $_ -match '^\s*([^#=]+)=(.*)$' } |
    ForEach-Object { $sozlama[$Matches[1].Trim()] = $Matches[2].Trim() }

Write-Host "GitHub: Jarvis loyihasi > Settings > Secrets and variables > Actions > New repository secret"
Write-Host ""
[Convert]::ToBase64String([IO.File]::ReadAllBytes($sozlama['storeFile'])) | Set-Clipboard
Write-Host "1) Nomi: JARVIS_KEYSTORE_BASE64  - qiymati buferda. Ctrl+V bilan qo'ying va saqlang."
Read-Host "   Tayyor bo'lsa Enter bosing"
$sozlama['storePassword'] | Set-Clipboard
Write-Host "2) Nomi: JARVIS_KEYSTORE_PASSWORD - qiymati buferda. Ctrl+V bilan qo'ying va saqlang."
Read-Host "   Tayyor bo'lsa Enter bosing"
Set-Clipboard -Value ' '
Write-Host "Bufer tozalandi. Endi Actions > 'Jarvis telefon APK' > Run workflow."
