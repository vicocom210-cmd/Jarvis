; ============================================================
;  Jarvis — o'rnatuvchi (Inno Setup 6)
;  Qanday ishlatiladi:
;    1) dist\Jarvis.exe tayyor bo'lsin (GitHub'dan yuklab oling yoki exe_qurish.bat)
;       va jarvis.ico shu papkada bo'lsin (belgi_yasa.py yasaydi)
;    2) Bu faylni Inno Setup'da oching va "Compile" (Ctrl+F9) bosing
;    3) Tayyor: Output\Jarvis-Setup.exe
;  Administrator huquqi shart emas — foydalanuvchining o'z papkasiga o'rnatiladi.
; ============================================================

#define Nomi       "Jarvis"
#ifndef Versiya
  #define Versiya  "3.0"
#endif
#define Muallif    "Abdulloh"
#define Dastur     "Jarvis.exe"

[Setup]
AppId={{8F3C2A51-6B7D-4E2A-9C1F-5A3D7E9B2C41}
AppName={#Nomi}
AppVersion={#Versiya}
AppVerName={#Nomi} {#Versiya}
AppPublisher={#Muallif}
AppComments=O'zbekcha ovozli yordamchi
DefaultDirName={autopf}\{#Nomi}
DefaultGroupName={#Nomi}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=Jarvis-Setup
SetupIconFile=jarvis.ico
UninstallDisplayIcon={app}\{#Dastur}
UninstallDisplayName={#Nomi}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; O'rnatish yoki o'chirishda ishlab turgan Jarvis yopiladi
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.Qoshimcha=Qo'shimcha:
english.IshStoli=Ish stolida yorliq yaratish
english.Avtostart=Kompyuter yonganda Jarvis o'zi ishga tushsin
english.HozirOch=Jarvis'ni hozir ishga tushirish
english.Ochirish=Jarvis'ni o'chirish
russian.Qoshimcha=Дополнительно:
russian.IshStoli=Создать ярлык на рабочем столе
russian.Avtostart=Запускать Jarvis вместе с Windows
russian.HozirOch=Запустить Jarvis сейчас
russian.Ochirish=Удалить Jarvis

[Tasks]
Name: "ishstoli";  Description: "{cm:IshStoli}";  GroupDescription: "{cm:Qoshimcha}"
Name: "avtostart"; Description: "{cm:Avtostart}"; GroupDescription: "{cm:Qoshimcha}"; Flags: unchecked

[Files]
Source: "dist\{#Dastur}"; DestDir: "{app}"; Flags: ignoreversion
Source: "jarvis.ico";     DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#Nomi}";        Filename: "{app}\{#Dastur}"; IconFilename: "{app}\jarvis.ico"
Name: "{group}\{cm:Ochirish}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nomi}";  Filename: "{app}\{#Dastur}"; IconFilename: "{app}\jarvis.ico"; Tasks: ishstoli
; Jarvis o'zi ham shu yorliqni taniydi (chatdagi "Windows bilan ishga tushsin" almashtirgichi)
Name: "{userstartup}\{#Nomi}";  Filename: "{app}\{#Dastur}"; Tasks: avtostart

[Run]
Filename: "{app}\{#Dastur}"; Description: "{cm:HozirOch}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; O'chirishdan oldin ishlab turgan Jarvis'ni to'xtatamiz
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#Dastur} /F"; Flags: runhidden; RunOnceId: "JarvisniTox"

[UninstallDelete]
; Jarvis o'zi yaratgan avtostart fayli (chatdagi almashtirgich orqali)
Type: files; Name: "{userstartup}\Jarvis.bat"
; Eslatma: sozlamalar va suhbat arxivi (%APPDATA%\Jarvis) o'chirilmaydi — qayta o'rnatsangiz saqlanib qoladi
