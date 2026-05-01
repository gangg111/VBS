#!/usr/bin/env python3
"""
VBS GUI — natywny GUI do zarządzania Virtualization-based Security w Windows.
Port logiki VBS.cmd v1.0 — wszystkie operacje wykonywane bezpośrednio z Pythona
przez WinReg i bcdedit. Zero okien konsoli.
"""

import os
import sys
import ctypes
import subprocess
import winreg
import platform
import tkinter as tk
from tkinter import messagebox, scrolledtext

# ── Ścieżki rejestru ──────────────────────────────────────────────────────────
HKLM   = winreg.HKEY_LOCAL_MACHINE
RD     = winreg.KEY_READ  | winreg.KEY_WOW64_64KEY
WR     = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY

DG     = r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
DG_S   = DG + r"\Scenarios"
LSA    = r"SYSTEM\CurrentControlSet\Control\Lsa"
MEM    = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
POL_DG = r"SOFTWARE\Policies\Microsoft\Windows\DeviceGuard"
MVBS   = r"SOFTWARE\ManageVBS"

# ── Wykrywanie motywu Windows ─────────────────────────────────────────────────
def _is_dark_theme() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize") as k:
            val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return val == 0
    except Exception:
        return False

_DARK = _is_dark_theme()

def _set_titlebar_theme(win) -> None:
    """Ustawia ciemny/jasny pasek tytułu zgodnie z motywem Windows (Win10 1809+)."""
    try:
        import ctypes.wintypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        if hwnd == 0:
            hwnd = win.winfo_id()
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if _DARK else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        # Starsze buildy Win10 używają atrybutu 19
        if not _DARK:
            return
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
    except Exception:
        pass

# ── Skalowanie DPI ────────────────────────────────────────────────────────────
_DPI_SCALE: float = 1.0

def _s(n) -> int:
    """Skaluje wartość pikselową do aktualnego DPI (96 dpi = skala 1.0)."""
    return round(n * _DPI_SCALE)

def _enable_dpi_awareness() -> None:
    """Rejestruje proces jako Per-Monitor V2 DPI-aware (przed tk.Tk())."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwarenessContext(-4)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def _apply_dpi_scaling(root) -> None:
    """Ustawia skalowanie czcionek tkinter wg DPI monitora (po tk.Tk())."""
    global _DPI_SCALE
    try:
        dpi = root.winfo_fpixels('1i')
        _DPI_SCALE = dpi / 96.0
        root.tk.call('tk', 'scaling', dpi / 72.0)
    except Exception:
        pass

_enable_dpi_awareness()

# ── Kolory (automatycznie jasny/ciemny według motywu Windows) ─────────────────
if _DARK:
    BG    = "#202020"; BG2  = "#2d2d2d"; BG3   = "#1a1a1a"
    SURF  = "#3d3d3d"; TEXT = "#f3f3f3"; SUB   = "#c0c0c0"; MUTED = "#888888"
    G_BG  = "#0f7b0f"; B_BG = "#0063b1"; O_BG  = "#c45000"
    C_OK  = "#6ccb5f"; C_ERR= "#ff6b6b"; C_WRN = "#f9c74f"
    C_INF = "#5ba3f5"; C_SKP= "#888888"
    INFO_FRAME_BG = "#1a2e44"
else:
    BG    = "#f3f3f3"; BG2  = "#ffffff"; BG3   = "#e8e8e8"
    SURF  = "#d0d0d0"; TEXT = "#1a1a1a"; SUB   = "#444444"; MUTED = "#888888"
    G_BG  = "#0f7b0f"; B_BG = "#0063b1"; O_BG  = "#c45000"
    C_OK  = "#107c10"; C_ERR= "#c42b1c"; C_WRN = "#9d5d00"
    C_INF = "#0063b1"; C_SKP= "#888888"
    INFO_FRAME_BG = "#dce8f5"

TAGS  = {"ok": C_OK, "err": C_ERR, "warn": C_WRN, "info": C_INF, "skip": C_SKP}
NO_WIN = 0x08000000  # CREATE_NO_WINDOW

# ── Język interfejsu ──────────────────────────────────────────────────────────
def _detect_lang() -> str:
    """Returns 'pl' if Windows UI language is Polish, else 'en'."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Control Panel\International") as k:
            val, _ = winreg.QueryValueEx(k, "LocaleName")
            return "pl" if str(val).lower().startswith("pl") else "en"
    except Exception:
        return "en"

_LANG = _detect_lang()

_S: dict = {
    "pl": {
        "subtitle":               "Zarządzanie zabezpieczeniami opartymi na wirtualizacji",
        "status_header":          "AKTUALNY STAN ZABEZPIECZEŃ",
        "refresh":                "⟳  Odśwież",
        "actions_header":         "AKCJE",
        "btn_disable":            "▶   Wyłącz zabezpieczenia Hypervisor",
        "btn_disable_desc":       "Wyłącza VBS, HVCI, CG, Hypervisor i inne",
        "confirm_disable_title":  "Wyłącz funkcje zabezpieczeń",
        "confirm_disable_msg": (
            "Skrypt wyłączy:\n"
            "  • VBS / HVCI / Credential Guard / System Guard\n"
            "  • Windows Hello / Windows Hypervisor / KVA Shadow\n\n"
            "⚠  Wyłącz Windows Hello przed kontynuowaniem!\n\n"
            "Wymagany będzie restart systemu. Kontynuować?"
        ),
        "btn_revert":             "↩   Cofnij zmiany",
        "btn_revert_desc":        "Przywraca poprzednio zmienione funkcje",
        "err_revert_title":       "Błąd cofania zmian",
        "btn_startup":            "⟳   Restart — Ustawienia uruchamiania",
        "btn_startup_desc":       "W Ustawieniach uruchamiania wciśnij 7 aby wyłączyć weryfikację sterowników",
        "confirm_startup_title":  "Restart — Ustawienia uruchamiania",
        "confirm_startup_msg": (
            "Komputer uruchomi się ponownie.\n"
            "Po restarcie wciśnij 7 aby wyłączyć weryfikację sterowników.\n\n"
            "⚠  Zapisz wszystkie otwarte pliki! Kontynuować?"
        ),
        "dot_active":             "● Aktywne",
        "dot_off":                "● Wyłączone",
        "dot_na":                 "● Nie dotyczy",
        "dot_unknown":            "● Brak danych",
        "status_admin":           "✔  Tryb administratora — operacje będą wykonane bezpośrednio",
        "status_user":            "⚠  Brak uprawnień administratora — przy każdej akcji pojawi się monit UAC",
        "warn_hello":             "⚠  Wyłącz Windows Hello (PIN / odcisk palca / twarz) przed kontynuowaniem.",
        "warn_anticheat":         "⚠  Gry z anty-cheatem (Valorant, FACEIT) mogą przestać działać po wyłączeniu zabezpieczeń.",
        "restart_required":       "Restart wymagany",
        "restart_body":           "Aby zmiany weszły w życie, uruchom\nponownie komputer.",
        "btn_continue":           "Kontynuuj",
        "btn_cancel":             "Anuluj",
        "security_disabled_title":"✔  Zabezpieczenia zostały wyłączone",
        "security_disabled_body": (
            "Aby zmiany weszły w życie, wymagany jest restart.\n\n"
            "Kliknij Kontynuuj — komputer uruchomi się ponownie\n"
            "i przejdzie do ekranu Ustawień uruchamiania.\n"
            "Wciśnij 7, aby wyłączyć wymuszanie podpisów sterowników."
        ),
        "btn_continue_startup":   "Kontynuuj — Ustawienia uruchamiania",
        "result_disable_fail":    "VBS — Wyłączanie funkcji zabezpieczeń  ✘",
        "result_startup":         "VBS — Restart do Ustawień uruchamiania",
        "btn_restart_now":        "Uruchom ponownie teraz",
        "btn_restart_later":      "Uruchom ponownie później",
        "btn_close":              "Zamknij",
        "info_dse": (
            "ℹ  Aby wyłączyć weryfikację podpisów sterowników,\n"
            "   po restarcie użyj przycisku  ⟳ Restart — Ustawienia uruchamiania  i wciśnij 7."
        ),
        "err_platform_title":     "Platforma",
        "err_platform_msg":       "Ten program działa tylko na Windows.",
        "err_title":              "Błąd",
        "err_generic":            "Operacja zakończyła się błędem.",
        "done_title":             "Gotowe",
        "done_msg":               "Operacja zakończona pomyślnie.",
        "err_uac_title":          "Błąd UAC",
        "win_only":               "Ten program działa tylko na Windows.",
    },
    "en": {
        "subtitle":               "Manage virtualization-based security features",
        "status_header":          "CURRENT SECURITY STATUS",
        "refresh":                "⟳  Refresh",
        "actions_header":         "ACTIONS",
        "btn_disable":            "▶   Disable Hypervisor Security",
        "btn_disable_desc":       "Disables VBS, HVCI, CG, Hypervisor and more",
        "confirm_disable_title":  "Disable Security Features",
        "confirm_disable_msg": (
            "The script will disable:\n"
            "  • VBS / HVCI / Credential Guard / System Guard\n"
            "  • Windows Hello / Windows Hypervisor / KVA Shadow\n\n"
            "⚠  Disable Windows Hello before continuing!\n\n"
            "A system restart will be required. Continue?"
        ),
        "btn_revert":             "↩   Revert changes",
        "btn_revert_desc":        "Restores previously changed features",
        "err_revert_title":       "Revert error",
        "btn_startup":            "⟳   Restart — Startup Settings",
        "btn_startup_desc":       "In Startup Settings press 7 to disable driver signature enforcement",
        "confirm_startup_title":  "Restart — Startup Settings",
        "confirm_startup_msg": (
            "Your computer will restart.\n"
            "After restart press 7 to disable driver signature enforcement.\n\n"
            "⚠  Save all open files! Continue?"
        ),
        "dot_active":             "● Active",
        "dot_off":                "● Disabled",
        "dot_na":                 "● Not applicable",
        "dot_unknown":            "● Unknown",
        "status_admin":           "✔  Running as administrator — operations will run directly",
        "status_user":            "⚠  Not an administrator — each action will trigger a UAC prompt",
        "warn_hello":             "⚠  Disable Windows Hello (PIN / fingerprint / face) before continuing.",
        "warn_anticheat":         "⚠  Anti-cheat games (Valorant, FACEIT) may stop working after disabling security.",
        "restart_required":       "Restart required",
        "restart_body":           "Restart your computer\nto apply the changes.",
        "btn_continue":           "Continue",
        "btn_cancel":             "Cancel",
        "security_disabled_title":"✔  Security features disabled",
        "security_disabled_body": (
            "A restart is required for changes to take effect.\n\n"
            "Click Continue — your computer will restart\n"
            "and boot into Startup Settings.\n"
            "Press 7 to disable driver signature enforcement."
        ),
        "btn_continue_startup":   "Continue — Startup Settings",
        "result_disable_fail":    "VBS — Disabling security features  ✘",
        "result_startup":         "VBS — Restart to Startup Settings",
        "btn_restart_now":        "Restart now",
        "btn_restart_later":      "Restart later",
        "btn_close":              "Close",
        "info_dse": (
            "ℹ  To disable driver signature enforcement,\n"
            "   after restart use  ⟳ Restart — Startup Settings  and press 7."
        ),
        "err_platform_title":     "Platform",
        "err_platform_msg":       "This program only runs on Windows.",
        "err_title":              "Error",
        "err_generic":            "The operation failed.",
        "done_title":             "Done",
        "done_msg":               "Operation completed successfully.",
        "err_uac_title":          "UAC Error",
        "win_only":               "This program only runs on Windows.",
    },
}


def T(key: str) -> str:
    """Returns translated string for the current interface language."""
    return _S[_LANG].get(key, _S["en"].get(key, key))


# ── Uprawnienia / re-launch ───────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _pythonw() -> str:
    """Zwraca pythonw.exe (bez konsoli) jeśli dostępne."""
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pyw = exe[:-10] + "pythonw.exe"
        if os.path.exists(pyw):
            return pyw
    return exe


def relaunch_as_admin(action: str) -> bool:
    """Uruchamia ten skrypt ponownie z podwyższonymi uprawnieniami z flagą --action."""
    script = os.path.abspath(__file__)
    params = f'"{script}" --action {action}'
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", _pythonw(), params, os.path.dirname(script), 1
        )
        return int(ret) > 32
    except Exception as e:
        messagebox.showerror(T("err_uac_title"), str(e))
        return False


# ── Narzędzia rejestr ─────────────────────────────────────────────────────────

def rget(sub: str, name: str):
    try:
        with winreg.OpenKey(HKLM, sub, 0, RD) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v
    except Exception:
        return None


def rset_dword(sub: str, name: str, val: int) -> bool:
    try:
        with winreg.CreateKeyEx(HKLM, sub, 0, WR) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, val)
        return True
    except Exception:
        return False


def rset_sz(sub: str, name: str, val: str) -> bool:
    try:
        with winreg.CreateKeyEx(HKLM, sub, 0, WR) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        return True
    except Exception:
        return False


def rdel(sub: str, name: str) -> bool:
    try:
        with winreg.OpenKey(HKLM, sub, 0, WR) as k:
            winreg.DeleteValue(k, name)
        return True
    except Exception:
        return False


# MVBS (ManageVBS) — skróty do stanu zapisanego przez skrypt
def mset(name: str, val=1):
    if isinstance(val, str):
        rset_sz(MVBS, name, val)
    else:
        rset_dword(MVBS, name, int(val))


def mget(name: str):
    return rget(MVBS, name)


def mclr(name: str):
    rdel(MVBS, name)


# ── bcdedit / PowerShell bez okna konsoli ─────────────────────────────────────

def bcdedit(*args) -> tuple:
    r = subprocess.run(
        ["bcdedit"] + list(args),
        capture_output=True, text=True, creationflags=NO_WIN
    )
    return r.returncode == 0, r.stdout


def ps(script: str) -> str:
    r = subprocess.run(
        ["powershell", "-nop", "-c", script],
        capture_output=True, text=True, creationflags=NO_WIN
    )
    return r.stdout.strip()


# ── Wykrywanie aktualnego stanu zabezpieczeń ────────────────────────────────────

def get_security_status() -> list:
    """
    Zwraca listę krotek (nazwa, aktywna: bool | None).
    Brak klucza w rejestrze = wyłączone (False) dla funkcji VBS.
    None tylko gdy stan jest naprawdę nieznany (KVA na nieznanym CPU).
    Odczyt nie wymaga uprawnień administratora (rejestr HKLM czytelny).
    """
    results = []

    def check_feat(label, key, val_name):
        """Brak klucza lub wartość 0 → False (wyłączone). Wartość 1 → True (aktywne)."""
        v = rget(key, val_name)
        results.append((label, v == 1))  # None i 0 oba dają False

    check_feat("Virtualization-based Security",
               DG, "EnableVirtualizationBasedSecurity")
    check_feat("Memory Integrity (HVCI)",
               f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Enabled")

    # Credential Guard — sprawdź też LSA
    cg_scen = rget(f"{DG_S}\\CredentialGuard", "Enabled") == 1
    cg_lsa  = rget(LSA, "LsaCfgFlags") == 1
    results.append(("Credential Guard", cg_scen or cg_lsa))

    check_feat("System Guard",
               f"{DG_S}\\SystemGuard", "Enabled")
    check_feat("Windows Hello Protection",
               f"{DG_S}\\WindowsHello", "Enabled")
    check_feat("Enhanced Sign-in Security",
               f"{DG_S}\\SecureBiometrics", "Enabled")

    # Hypervisor — bcdedit + WMI jako fallback
    r = subprocess.run(
        ["bcdedit", "/enum", "{current}"],
        capture_output=True, text=True, creationflags=NO_WIN
    )
    hyp_bcd = None
    for line in r.stdout.splitlines():
        if "hypervisorlaunchtype" in line.lower():
            hyp_bcd = line.split()[-1].lower()
    if hyp_bcd is not None:
        hyp_active = hyp_bcd in ("auto", "on")
    else:
        # klucz nieobecny → sprawdź czy hypervisor faktycznie działa przez WMI
        hyp_wmi = ps("(gcim Win32_ComputerSystem).HypervisorPresent")
        hyp_active = hyp_wmi.lower() == "true"
    results.append(("Windows Hypervisor", hyp_active))

    # KVA Shadow — najpierw sprawdź czy CPU w ogóle tego wymaga
    kva_needed = ps(
        "$d=Add-Type -MemberDefinition "
        "'[DllImport(\"ntdll.dll\")] public static extern int "
        "NtQuerySystemInformation(uint a,IntPtr b,uint c,IntPtr d);' "
        "-Name n -Namespace w -PassThru;"
        "$p=[Runtime.InteropServices.Marshal]::AllocHGlobal(4);"
        "$r=[Runtime.InteropServices.Marshal]::AllocHGlobal(4);"
        "$ret=$d::NtQuerySystemInformation(196,$p,4,$r);"
        "if($ret -eq 0){"
        "$f=[uint32][Runtime.InteropServices.Marshal]::ReadInt32($p);"
        "if(($f -band 0x01)-ne 0 -or "
        "(($f -band 0x20)-ne 0 -and ($f -band 0x10)-ne 0))"
        "{Write-Output 1}else{Write-Output 0}}else{Write-Output 0}"
    ).strip() == "1"

    if not kva_needed:
        results.append(("KVA Shadow", False))  # CPU nie wymaga — nie dotyczy
    else:
        kva1 = rget(MEM, "FeatureSettingsOverride")
        kva2 = rget(MEM, "FeatureSettingsOverrideMask")
        kva_disabled = (kva1 == 2 and kva2 == 3)
        results.append(("KVA Shadow", not kva_disabled))

    return results


# ── Log (wpisy z kolorami) ────────────────────────────────────────────────────

class Log:
    def __init__(self):
        self.entries: list = []

    def ok(self, m):   self.entries.append((m, "ok"))
    def err(self, m):  self.entries.append((m, "err"))
    def warn(self, m): self.entries.append((m, "warn"))
    def info(self, m): self.entries.append((m, "info"))
    def skip(self, m): self.entries.append((m, "skip"))


# ── Akcja: wyłącz VBS i powiązane funkcje ────────────────────────────────────

def do_continue(log: Log) -> bool:
    """Port sekcji :dk_showosinfo z VBS.cmd — wyłącza VBS i powiązane funkcje."""

    # Wirtualizacja
    hyp = ps("(gcim Win32_ComputerSystem).HypervisorPresent")
    vtx = ps("(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled")
    if hyp.lower() == "true":
        vtx = "True"
    if vtx.lower() != "true":
        log.err("Wirtualizacja (VT-x/SVM) nie jest włączona w BIOS.")
        log.warn("Włącz wirtualizację w ustawieniach BIOS/UEFI.")
        return False
    log.ok(f"{'Wirtualizacja':<36}[Włączona]")

    # Blokady UEFI
    vbs_lck  = rget(DG, "Locked") == 1
    hvci_lck = rget(f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Locked") == 1
    cg_lck   = rget(LSA, "LsaCfgFlags") == 1
    mand_lck = rget(DG, "Mandatory") == 1

    if vbs_lck or hvci_lck or cg_lck:
        log.err("Wykryto blokadę UEFI na jednej lub kilku funkcjach.")
        log.warn("Obsługa blokad UEFI wymaga SecConfig.efi — użyj VBS.cmd.")
        return False

    if mand_lck:
        if rset_dword(DG, "Mandatory", 0):
            log.ok(f"{'Tryb obowiązkowy (Mandatory)':<36}[Wyłączony]")
        else:
            log.err(f"{'Tryb obowiązkowy (Mandatory)':<36}[Błąd]")
            return False

    changed = False
    errors  = False

    def disable_reg(label: str, key: str, val_name: str, save_key: str):
        nonlocal changed, errors
        if rget(key, val_name) == 1:
            log.info(f"{label:<36}[Znaleziono]")
            mset(save_key)
            if rset_dword(key, val_name, 0):
                log.ok(f"{label:<36}[Wyłączono]")
                changed = True
            else:
                log.err(f"{label:<36}[Błąd]")
                mclr(save_key)
                errors = True

    # Windows Hello
    disable_reg("Windows Hello Protection",
                f"{DG_S}\\WindowsHello", "Enabled", "WindowsHello")

    # Enhanced Sign-in Security
    if rget(f"{DG_S}\\SecureBiometrics", "Enabled") == 1:
        log.info(f"{'Enhanced Sign-in Security':<36}[Znaleziono]")
        mset("SecureBiometrics")
        if rget(DG_S, "SecureBiometrics") == 1:
            mset("SecureBiometricsScenario")
            rset_dword(DG_S, "SecureBiometrics", 0)
        if rset_dword(f"{DG_S}\\SecureBiometrics", "Enabled", 0):
            log.ok(f"{'Enhanced Sign-in Security':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Enhanced Sign-in Security':<36}[Błąd]")
            mclr("SecureBiometrics"); mclr("SecureBiometricsScenario")
            errors = True

    # Virtualization-based Security
    vbs_val  = rget(DG, "EnableVirtualizationBasedSecurity")
    rpsf_val = rget(DG, "RequirePlatformSecurityFeatures")
    if vbs_val == 1:
        log.info(f"{'Virtualization-based Security':<36}[Znaleziono]")
        mset("VBS")
        if rpsf_val is not None:
            mset("RequirePlatformSecurityFeatures", rpsf_val)
            rdel(DG, "RequirePlatformSecurityFeatures")
        if rset_dword(DG, "EnableVirtualizationBasedSecurity", 0):
            log.ok(f"{'Virtualization-based Security':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Virtualization-based Security':<36}[Błąd]")
            mclr("VBS"); mclr("RequirePlatformSecurityFeatures")
            errors = True

    # System Guard
    disable_reg("System Guard",
                f"{DG_S}\\SystemGuard", "Enabled", "SystemGuard")

    # Memory Integrity (HVCI)
    hvci_svc = ps("(Get-CimInstance Win32_DeviceGuard "
                  "-Namespace root\\Microsoft\\Windows\\DeviceGuard)"
                  ".SecurityServicesRunning")
    hvci_reg = rget(f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Enabled")
    if "2" in hvci_svc.split() or hvci_reg == 1:
        log.info(f"{'Memory Integrity (HVCI)':<36}[Znaleziono]")
        mset("HVCI")
        if rset_dword(f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Enabled", 0):
            log.ok(f"{'Memory Integrity (HVCI)':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Memory Integrity (HVCI)':<36}[Błąd]")
            mclr("HVCI"); errors = True

    # Credential Guard
    cg_svc  = ps("(Get-CimInstance Win32_DeviceGuard "
                 "-Namespace root\\Microsoft\\Windows\\DeviceGuard)"
                 ".SecurityServicesRunning")
    cg_scen = rget(f"{DG_S}\\CredentialGuard", "Enabled") == 1
    if "1" in cg_svc.split():
        log.info(f"{'Credential Guard':<36}[Znaleziono]")
        mset("CredentialGuard")
        ok1 = rset_dword(LSA, "LsaCfgFlags", 0)
        ok2 = rset_dword(POL_DG, "LsaCfgFlags", 0)
        if ok1 and ok2:
            log.ok(f"{'Credential Guard':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Credential Guard':<36}[Błąd]")
            mclr("CredentialGuard"); errors = True
    if cg_scen:
        log.info(f"{'Credential Guard Scenarios':<36}[Znaleziono]")
        mset("CredentialGuardScenario")
        if rset_dword(f"{DG_S}\\CredentialGuard", "Enabled", 0):
            log.ok(f"{'Credential Guard Scenarios':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Credential Guard Scenarios':<36}[Błąd]")
            mclr("CredentialGuardScenario"); errors = True

    # KVA Shadow (starsze Intel CPU)
    kva_raw = ps(
        "$d=Add-Type -MemberDefinition "
        "'[DllImport(\"ntdll.dll\")] public static extern int "
        "NtQuerySystemInformation(uint a,IntPtr b,uint c,IntPtr d);' "
        "-Name n -Namespace w -PassThru;"
        "$p=[Runtime.InteropServices.Marshal]::AllocHGlobal(4);"
        "$r=[Runtime.InteropServices.Marshal]::AllocHGlobal(4);"
        "$ret=$d::NtQuerySystemInformation(196,$p,4,$r);"
        "if($ret -eq 0){"
        "$f=[uint32][Runtime.InteropServices.Marshal]::ReadInt32($p);"
        "if(($f -band 0x01)-ne 0 -or "
        "(($f -band 0x20)-ne 0 -and ($f -band 0x10)-ne 0))"
        "{Write-Output 1}else{Write-Output 0}}else{Write-Output 0}"
    )
    if kva_raw.strip() == "1":
        kva1 = rget(MEM, "FeatureSettingsOverride")
        kva2 = rget(MEM, "FeatureSettingsOverrideMask")
        if not (kva1 == 2 and kva2 == 3):
            log.info(f"{'KVA Shadow':<36}[Znaleziono]")
            ok = (rset_dword(MVBS, "KVAShadow", 1)
                  and rset_dword(MEM, "FeatureSettingsOverride", 2)
                  and rset_dword(MEM, "FeatureSettingsOverrideMask", 3))
            if ok:
                log.ok(f"{'KVA Shadow':<36}[Wyłączono]")
                changed = True
            else:
                log.err(f"{'KVA Shadow':<36}[Błąd]")
                mclr("KVAShadow"); errors = True

    # Windows Hypervisor
    _, hyp_out = bcdedit("/enum", "{current}")
    hyp_bcd = None
    for line in hyp_out.splitlines():
        if "hypervisorlaunchtype" in line.lower():
            hyp_bcd = line.split()[-1]
    hyp_needed = False
    if hyp_bcd is None:
        vbs_st = ps("(Get-CimInstance Win32_DeviceGuard "
                    "-Namespace root\\Microsoft\\Windows\\DeviceGuard)"
                    ".VirtualizationBasedSecurityStatus")
        hyp_ps = ps("(Get-CimInstance Win32_ComputerSystem).HypervisorPresent")
        if vbs_st in ("1", "2") and hyp_ps.lower() == "true":
            hyp_needed = True
    elif hyp_bcd.lower() in ("auto", "on"):
        hyp_needed = True

    if hyp_needed:
        log.info(f"{'Windows Hypervisor':<36}[Znaleziono]")
        mset("Hypervisor")
        if hyp_bcd:
            mset("HypervisorLaunchType", hyp_bcd)
        ok, _ = bcdedit("/set", "hypervisorlaunchtype", "off")
        if ok:
            log.ok(f"{'Windows Hypervisor':<36}[Wyłączono]")
            changed = True
        else:
            log.err(f"{'Windows Hypervisor':<36}[Błąd]")
            mclr("Hypervisor"); mclr("HypervisorLaunchType"); errors = True

    if errors:
        log.err("\nNiektóre operacje zakończyły się błędem.")
        log.warn("Użyj opcji 'Cofnij zmiany' aby przywrócić poprzedni stan.")
        return False

    if not changed:
        log.skip("\nWszystkie funkcje są już wyłączone — brak zmian.")
        log.info("System zostanie skierowany do Startup Settings po restarcie.")

    bcdedit("/set", "{current}", "onetimeadvancedoptions", "on")
    log.ok("\nOpcje startowe ustawione.")
    log.warn("Po restarcie wciśnij 7, aby wyłączyć DSE.")
    log.info("Wymagany restart systemu.")
    return True


# ── Akcja: cofnij zmiany ──────────────────────────────────────────────────────

def do_revert(log: Log) -> bool:
    """Port sekcji :dk_revert z VBS.cmd — przywraca wyłączone funkcje."""

    # Sprawdź czy jest co cofać
    has = False
    try:
        with winreg.OpenKey(HKLM, MVBS, 0, RD) as k:
            i = 0
            while True:
                try:
                    nm, _, _ = winreg.EnumValue(k, i)
                    if nm.lower() != "uefilockagreed":
                        has = True; break
                    i += 1
                except OSError:
                    break
    except Exception:
        pass

    if not has:
        log.warn("Brak zmian do cofnięcia.")
        log.skip("Skrypt nie był wcześniej uruchamiany lub nic nie wyłączono.")
        return True

    errors = False

    def restore(label: str, fn, save_key: str):
        nonlocal errors
        if mget(save_key) == 1:
            if fn():
                log.ok(f"{label:<36}[Przywrócono]")
                mclr(save_key)
            else:
                log.err(f"{label:<36}[Błąd]")
                errors = True

    restore("VBS UEFI Lock",
            lambda: rset_dword(DG, "Locked", 1), "VBSLocked")
    restore("HVCI UEFI Lock",
            lambda: rset_dword(
                f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Locked", 1),
            "HVCILocked")
    restore("Credential Guard UEFI Lock",
            lambda: (rset_dword(DG, "EnableVirtualizationBasedSecurity", 1)
                     and rset_dword(DG, "RequirePlatformSecurityFeatures", 3)
                     and rset_dword(LSA, "LsaCfgFlags", 1)
                     and rset_dword(f"{DG_S}\\CredentialGuard", "Enabled", 1)),
            "CGLocked")

    # Hypervisor
    if mget("Hypervisor") == 1:
        htype = mget("HypervisorLaunchType")
        if htype is None:
            ok, _ = bcdedit("/deletevalue", "{current}", "hypervisorlaunchtype")
            if not ok:
                ok = True  # wartość mogła nie istnieć, to OK
        else:
            ok, _ = bcdedit("/set", "hypervisorlaunchtype", str(htype))
        if ok:
            log.ok(f"{'Windows Hypervisor':<36}[Przywrócono]")
            mclr("Hypervisor"); mclr("HypervisorLaunchType")
        else:
            log.err(f"{'Windows Hypervisor':<36}[Błąd]")
            errors = True

    # KVA Shadow
    if mget("KVAShadow") == 1:
        if rdel(MEM, "FeatureSettingsOverride") and rdel(MEM, "FeatureSettingsOverrideMask"):
            log.ok(f"{'KVA Shadow':<36}[Przywrócono]")
            mclr("KVAShadow")
        else:
            log.err(f"{'KVA Shadow':<36}[Błąd]")
            errors = True

    # Credential Guard
    if mget("CredentialGuard") == 1:
        rdel(LSA, "LsaCfgFlags"); rdel(POL_DG, "LsaCfgFlags")
        log.ok(f"{'Credential Guard':<36}[Przywrócono]")
        mclr("CredentialGuard")

    restore("Credential Guard Scenarios",
            lambda: rset_dword(f"{DG_S}\\CredentialGuard", "Enabled", 1),
            "CredentialGuardScenario")
    restore("Memory Integrity (HVCI)",
            lambda: rset_dword(
                f"{DG_S}\\HypervisorEnforcedCodeIntegrity", "Enabled", 1),
            "HVCI")
    restore("System Guard",
            lambda: rset_dword(f"{DG_S}\\SystemGuard", "Enabled", 1),
            "SystemGuard")

    # VBS
    if mget("VBS") == 1:
        rpsf = mget("RequirePlatformSecurityFeatures")
        ok = rset_dword(DG, "EnableVirtualizationBasedSecurity", 1)
        if rpsf is not None:
            rset_dword(DG, "RequirePlatformSecurityFeatures", int(rpsf))
            mclr("RequirePlatformSecurityFeatures")
        if ok:
            log.ok(f"{'Virtualization-based Security':<36}[Przywrócono]")
            mclr("VBS")
        else:
            log.err(f"{'Virtualization-based Security':<36}[Błąd]")
            errors = True

    restore("Enhanced Sign-in Security",
            lambda: rset_dword(f"{DG_S}\\SecureBiometrics", "Enabled", 1),
            "SecureBiometrics")
    if mget("SecureBiometricsScenario") == 1:
        rset_dword(DG_S, "SecureBiometrics", 1)
        mclr("SecureBiometricsScenario")

    restore("Windows Hello Protection",
            lambda: rset_dword(f"{DG_S}\\WindowsHello", "Enabled", 1),
            "WindowsHello")

    if errors:
        log.err("\nNiektóre operacje zakończyły się błędem.")
        return False

    log.ok("\nWszystkie zmiany cofnięte pomyślnie.")
    log.info("Wymagany restart systemu, aby zmiany weszły w życie.")
    return True


# ── Akcja: restart do Startup Settings ───────────────────────────────────────

def do_restart_startup(log: Log) -> bool:
    """Port sekcji :dk_restart_startup — restart do Startup Settings (7)."""
    ok, _ = bcdedit("/set", "{current}", "onetimeadvancedoptions", "on")
    if ok:
        log.ok("Opcje startowe ustawione.")
        log.warn("Po restarcie wciśnij 7, aby wyłączyć DSE.")
        log.info("System uruchomi się ponownie za 5 sekund...")
        subprocess.Popen(
            ["shutdown", "/r", "/t", "5"],
            creationflags=NO_WIN
        )
        return True
    else:
        log.err("Nie udało się ustawić opcji startowych (bcdedit).")
        return False


# ── Okno wyników ──────────────────────────────────────────────────────────────

def show_result_window(title: str, log: Log, ask_restart=False, parent=None):
    if parent is not None:
        win = tk.Toplevel(parent)
        win.grab_set()
    else:
        win = tk.Tk()
    win.title(title)
    win.configure(bg=BG)
    win.geometry(f"{_s(660)}x{_s(430)}")
    win.resizable(True, True)
    win.update_idletasks()
    _set_titlebar_theme(win)

    tk.Label(win, text=title, font=("Segoe UI", 11, "bold"),
             fg=TEXT, bg=BG).pack(pady=(12, 6))

    txt = scrolledtext.ScrolledText(
        win, font=("Consolas", 9), bg=BG2, fg=TEXT,
        bd=0, relief="flat", padx=10, pady=8, wrap=tk.WORD
    )
    txt.pack(fill=tk.BOTH, expand=True, padx=16)
    for tag, color in TAGS.items():
        txt.tag_configure(tag, foreground=color)
    for msg, tag in log.entries:
        txt.insert(tk.END, msg + "\n", tag)
    txt.configure(state="disabled")

    btn_row = tk.Frame(win, bg=BG)
    btn_row.pack(pady=12)

    def _btn(text, cmd, bg=SURF, fg=TEXT, bold=False):
        f = ("Segoe UI", 9, "bold") if bold else ("Segoe UI", 9)
        tk.Button(btn_row, text=text, command=cmd, font=f,
                  bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                  relief="flat", bd=0, padx=14, pady=7,
                  cursor="hand2").pack(side=tk.LEFT, padx=5)

    if ask_restart:
        info = tk.Frame(win, bg=INFO_FRAME_BG, padx=12, pady=8)
        info.pack(fill=tk.X, padx=16, pady=(6, 2))
        tk.Label(info,
                 text="ℹ  Aby wyłączyć wymuszanie podpisów sterowników (DSE),\n"
                      "   po restarcie użyj przycisku  ⟳ Restart do Startup Settings  i wciśnij 7.",
                 font=("Segoe UI", 9), fg=C_INF, bg=INFO_FRAME_BG,
                 justify="left", anchor="w").pack(anchor="w")

        def restart_now():
            win.destroy()
            subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=NO_WIN)
        _btn("Uruchom ponownie teraz",  restart_now, bg=G_BG, fg="white", bold=True)
        _btn("Uruchom ponownie później", win.destroy)
    else:
        _btn("Zamknij", win.destroy)

    if parent is None:
        win.mainloop()


# ── Tryb elevated (--action) ──────────────────────────────────────────────────

def run_action_mode(action: str):
    """Wywołane w podwyższonym procesie — wykonuje akcję i pokazuje wyniki."""
    log = Log()

    if action == "revert":
        success = do_revert(log)
        errors = [m for m, t in log.entries if t == "err"]
        if errors:
            _minimal_tk_error(T("err_revert_title"), "\n".join(errors))
            return
        if success:
            _minimal_tk_restart_ask()
        return

    if action == "continue":
        success = do_continue(log)
        if success:
            _minimal_tk_continue_restart_ask()
            return
        # błąd — pokaż okno z logiem
        show_result_window(T("result_disable_fail"), log, ask_restart=False)
        return
    elif action == "restart_startup":
        success = do_restart_startup(log)
        ask_restart = False
    else:
        return

    title = {
        "restart_startup": T("result_startup"),
    }.get(action, "VBS")
    show_result_window(
        title + ("  ✔" if success else "  ✘"),
        log, ask_restart=False
    )


def _minimal_tk_error(title: str, msg: str):
    root = tk.Tk(); root.withdraw()
    messagebox.showerror(title, msg)
    root.destroy()


def _minimal_tk_restart_ask():
    """Minimalne okno restartu (dla akcji 'revert')."""
    root = tk.Tk()
    root.title(T("restart_required"))
    root.configure(bg=BG)
    root.resizable(False, False)
    root.geometry(f"{_s(320)}x{_s(140)}")
    root.eval("tk::PlaceWindow . center")
    root.update_idletasks()
    _apply_dpi_scaling(root)
    _set_titlebar_theme(root)

    tk.Label(root, text=T("restart_required"),
             font=("Segoe UI", 11, "bold"), fg=TEXT, bg=BG).pack(pady=(18, 6))
    tk.Label(root, text=T("restart_body"),
             font=("Segoe UI", 9), fg=SUB, bg=BG).pack()

    btn_row = tk.Frame(root, bg=BG)
    btn_row.pack(pady=(14, 0))

    def do_restart():
        root.destroy()
        subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=NO_WIN)

    tk.Button(btn_row, text=T("btn_continue"), command=do_restart,
              font=("Segoe UI", 9, "bold"), bg=G_BG, fg="white",
              activebackground=G_BG, relief="flat", bd=0,
              padx=18, pady=7, cursor="hand2").pack(side=tk.LEFT, padx=8)
    tk.Button(btn_row, text=T("btn_cancel"), command=root.destroy,
              font=("Segoe UI", 9), bg=SURF, fg=TEXT,
              activebackground="#b8b8b8", relief="flat", bd=0,
              padx=18, pady=7, cursor="hand2").pack(side=tk.LEFT, padx=8)

    root.mainloop()


def _minimal_tk_continue_restart_ask(parent=None):
    """Małe okno po wyłączeniu zabezpieczeń — restart do Startup Settings."""
    if parent is not None:
        win = tk.Toplevel(parent)
        win.grab_set()
        win.focus_force()
        parent.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = _s(420), _s(220)
        win.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")
    else:
        win = tk.Tk()
        win.geometry(f"{_s(420)}x{_s(220)}")
        win.eval("tk::PlaceWindow . center")
        win.update_idletasks()
        _apply_dpi_scaling(win)

    win.title(T("restart_required"))
    win.configure(bg=BG)
    win.resizable(False, False)
    win.update_idletasks()
    _set_titlebar_theme(win)

    tk.Label(win, text=T("security_disabled_title"),
             font=("Segoe UI", 11, "bold"), fg=C_OK, bg=BG).pack(pady=(18, 8))
    tk.Label(win,
             text=T("security_disabled_body"),
             font=("Segoe UI", 9), fg=SUB, bg=BG, justify="center").pack(padx=20)

    btn_row = tk.Frame(win, bg=BG)
    btn_row.pack(pady=(16, 0))

    def do_restart():
        win.destroy()
        bcdedit("/set", "{current}", "onetimeadvancedoptions", "on")
        subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=NO_WIN)

    tk.Button(btn_row, text=T("btn_continue_startup"), command=do_restart,
              font=("Segoe UI", 9, "bold"), bg=O_BG, fg="white",
              activebackground=O_BG, relief="flat", bd=0,
              padx=14, pady=7, cursor="hand2").pack(side=tk.LEFT, padx=8)
    tk.Button(btn_row, text=T("btn_cancel"), command=win.destroy,
              font=("Segoe UI", 9), bg=SURF, fg=TEXT,
              activebackground="#b8b8b8", relief="flat", bd=0,
              padx=14, pady=7, cursor="hand2").pack(side=tk.LEFT, padx=8)

    if parent is None:
        win.mainloop()


# ── Wywołanie akcji z GUI ─────────────────────────────────────────────────────

def trigger_action(action: str, confirm_title: str, confirm_msg: str, root=None):
    if not is_windows():
        messagebox.showerror(T("err_platform_title"), T("err_platform_msg"))
        return
    if not messagebox.askokcancel(confirm_title, confirm_msg, icon="warning"):
        return

    if is_admin():
        log = Log()
        ask_restart = False
        if action == "continue":
            success = do_continue(log); ask_restart = success
        elif action == "revert":
            success = do_revert(log); ask_restart = success
        elif action == "restart_startup":
            success = do_restart_startup(log)
            return
        else:
            return

        errors = [m for m, t in log.entries if t == "err"]
        if not success or errors:
            messagebox.showerror(
                T("err_title"),
                "\n".join(errors) if errors else T("err_generic")
            )
            return

        if ask_restart:
            _minimal_tk_continue_restart_ask(parent=root)
        else:
            messagebox.showinfo(T("done_title"), T("done_msg"))
    else:
        relaunch_as_admin(action)


# ── Główne okno GUI ───────────────────────────────────────────────────────────

def _make_action_row(parent, text, desc, bg_col, cmd):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill=tk.X, padx=22, pady=3)
    btn = tk.Button(row, text=text, command=cmd,
              font=("Segoe UI", 10, "bold"), width=34, anchor="w",
              bg=bg_col, fg="white", activebackground=bg_col, activeforeground="white",
              relief="flat", bd=0, padx=12, pady=9,
              cursor="hand2")
    btn.pack(side=tk.LEFT)
    tk.Label(row, text=desc, font=("Segoe UI", 9),
             fg=SUB, bg=BG, anchor="w").pack(side=tk.LEFT, padx=12)
    return btn


def main():
    root = tk.Tk()
    root.withdraw()  # ukryj okno podczas budowania UI
    root.title("VBS 1.0")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.update_idletasks()
    _apply_dpi_scaling(root)
    _set_titlebar_theme(root)

    def _build():
        global _LANG
        for w in root.winfo_children():
            w.destroy()

        # ── Przycisk zmiany języka w prawym górnym rogu ────────────────────────
        def _toggle_lang():
            global _LANG
            _LANG = "en" if _LANG == "pl" else "pl"
            _build()

        lang_label = "English" if _LANG == "pl" else "Polski"
        btn_lang = tk.Button(root, text=lang_label, command=_toggle_lang,
                             font=("Segoe UI", 8), bg=SURF, fg=SUB,
                             activebackground="#b8b8b8", activeforeground=TEXT,
                             relief="flat", bd=0, padx=10, pady=3, cursor="hand2")
        btn_lang.place(relx=1.0, y=10, x=-10, anchor="ne")

        tk.Label(root, text="VBS 1.0 — Virtualization-based Security",
                 font=("Segoe UI", 13, "bold"), fg=TEXT, bg=BG).pack(pady=(16, 2))
        tk.Label(root, text=T("subtitle"),
                 font=("Segoe UI", 9), fg=SUB, bg=BG).pack(pady=(0, 8))

        # ── Panel statusu ──────────────────────────────────────────────────────
        tk.Label(root, text=T("status_header"),
                 font=("Segoe UI", 8, "bold"), fg=MUTED, bg=BG).pack(pady=(4, 2))

        status_frame = tk.Frame(root, bg=BG2)
        status_frame.pack(fill=tk.X, padx=22, pady=(0, 4))

        status_labels: dict = {}  # name -> tk.Label

        grid = tk.Frame(status_frame, bg=BG2)
        grid.pack(fill=tk.X, padx=10, pady=8)

        def _status_dot(val) -> tuple:
            if val is True:   return (T("dot_active"),   C_ERR)
            if val is False:  return (T("dot_off"),      C_OK)
            if val == "na":   return (T("dot_na"),       C_INF)
            return (T("dot_unknown"), MUTED)

        initial = get_security_status()
        col_count = 2
        for i, (name, active) in enumerate(initial):
            row_i, col_i = divmod(i, col_count)
            cell = tk.Frame(grid, bg=BG2)
            cell.grid(row=row_i, column=col_i, sticky="w", padx=(4, 20), pady=2)
            tk.Label(cell, text=name, font=("Segoe UI", 9),
                     fg=SUB, bg=BG2, width=28, anchor="w").pack(side=tk.LEFT)
            dot_txt, dot_col = _status_dot(active)
            lbl = tk.Label(cell, text=dot_txt, font=("Segoe UI", 9, "bold"),
                           fg=dot_col, bg=BG2, anchor="w")
            lbl.pack(side=tk.LEFT)
            status_labels[name] = lbl

        def all_features_disabled() -> bool:
            return all(v is False for _, v in get_security_status())

        def has_changes_to_revert() -> bool:
            try:
                with winreg.OpenKey(HKLM, MVBS, 0, RD) as k:
                    i = 0
                    while True:
                        try:
                            nm, _, _ = winreg.EnumValue(k, i)
                            if nm.lower() != "uefilockagreed":
                                return True
                            i += 1
                        except OSError:
                            break
            except Exception:
                pass
            return False

        _updaters = []  # forward refs do funkcji aktualizujących przyciski

        def refresh_status():
            for name, active in get_security_status():
                lbl = status_labels.get(name)
                if lbl:
                    txt, col = _status_dot(active)
                    lbl.config(text=txt, fg=col)
            for fn in _updaters:
                fn()

        refresh_btn = tk.Button(
            status_frame, text=T("refresh"), command=refresh_status,
            font=("Segoe UI", 8), bg=SURF, fg=SUB,
            activebackground="#b8b8b8", activeforeground=TEXT,
            relief="flat", bd=0, padx=10, pady=3, cursor="hand2"
        )
        refresh_btn.pack(anchor="e", padx=10, pady=(0, 6))

        # ── Ostrzeżenia ────────────────────────────────────────────────────────
        tk.Frame(root, height=1, bg=SURF).pack(fill=tk.X, padx=22, pady=(4, 2))
        fi = tk.Frame(root, bg=BG2)
        fi.pack(fill=tk.X, padx=22, pady=(0, 6))
        box = scrolledtext.ScrolledText(fi, height=2, wrap=tk.WORD,
                                        font=("Segoe UI", 9), bg=BG2, fg=TEXT,
                                        bd=0, relief="flat", padx=10, pady=6)
        box.pack(fill=tk.X, padx=2, pady=2)

        def _refresh_warnings():
            box.configure(state="normal")
            box.delete("1.0", tk.END)
            lines = []
            hello_on = dict(get_security_status()).get("Windows Hello Protection", False)
            if hello_on:
                lines.append(T("warn_hello"))
            lines.append(T("warn_anticheat"))
            box.insert("1.0", "\n".join(lines))
            # dopasuj wysokość: 1 lub 2 linie
            box.configure(state="disabled", height=len(lines))

        _refresh_warnings()
        _updaters.append(_refresh_warnings)

        tk.Frame(root, height=1, bg=SURF).pack(fill=tk.X, padx=22, pady=4)
        tk.Label(root, text=T("actions_header"), font=("Segoe UI", 8, "bold"),
                 fg=MUTED, bg=BG).pack(pady=(2, 1))

        btn_continue = _make_action_row(root,
            T("btn_disable"),
            T("btn_disable_desc"),
            G_BG,
            lambda: trigger_action(
                "continue", T("confirm_disable_title"),
                T("confirm_disable_msg"),
                root=root
            )
        )

        def _update_continue_btn():
            if all_features_disabled():
                btn_continue.config(
                    state="disabled", bg=SURF, fg=MUTED,
                    activebackground=SURF, cursor=""
                )
            else:
                btn_continue.config(
                    state="normal", bg=G_BG, fg="white",
                    activebackground=G_BG, cursor="hand2"
                )

        _update_continue_btn()
        _updaters.append(_update_continue_btn)

        def run_revert_silent():
            if not is_windows():
                return
            def _do():
                if is_admin():
                    log = Log()
                    success = do_revert(log)
                    errors = [m for m, t in log.entries if t == "err"]
                    if errors:
                        root.after(0, lambda: messagebox.showerror(T("err_revert_title"), "\n".join(errors)))
                        return
                    root.after(0, refresh_status)
                    root.after(0, _ask_restart)
                else:
                    relaunch_as_admin("revert")

            def _ask_restart():
                win = tk.Toplevel(root)
                win.title(T("restart_required"))
                win.configure(bg=BG)
                win.resizable(False, False)
                win.grab_set()
                win.focus_force()
                win.update_idletasks()
                _set_titlebar_theme(win)

                root.update_idletasks()
                rx, ry, rw, rh = root.winfo_x(), root.winfo_y(), root.winfo_width(), root.winfo_height()
                w, h = _s(320), _s(140)
                win.geometry(f"{w}x{h}+{rx + (rw - w)//2}+{ry + (rh - h)//2}")

                tk.Label(win, text=T("restart_required"),
                         font=("Segoe UI", 11, "bold"), fg=TEXT, bg=BG).pack(pady=(18, 6))
                tk.Label(win, text=T("restart_body"),
                         font=("Segoe UI", 9), fg=SUB, bg=BG).pack()

                btn_row = tk.Frame(win, bg=BG)
                btn_row.pack(pady=(14, 0))

                def do_restart():
                    win.destroy()
                    subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=NO_WIN)

                tk.Button(btn_row, text=T("btn_continue"), command=do_restart,
                          font=("Segoe UI", 9, "bold"), bg=G_BG, fg="white",
                          activebackground=G_BG, activeforeground="white",
                          relief="flat", bd=0, padx=18, pady=7,
                          cursor="hand2").pack(side=tk.LEFT, padx=8)
                tk.Button(btn_row, text=T("btn_cancel"), command=win.destroy,
                          font=("Segoe UI", 9), bg=SURF, fg=TEXT,
                          activebackground="#b8b8b8", activeforeground=TEXT,
                          relief="flat", bd=0, padx=18, pady=7,
                          cursor="hand2").pack(side=tk.LEFT, padx=8)

            import threading
            threading.Thread(target=_do, daemon=True).start()

        btn_revert = _make_action_row(root,
            T("btn_revert"),
            T("btn_revert_desc"),
            B_BG,
            run_revert_silent
        )

        def _update_revert_btn():
            if has_changes_to_revert():
                btn_revert.config(
                    state="normal", bg=B_BG, fg="white",
                    activebackground=B_BG, cursor="hand2"
                )
            else:
                btn_revert.config(
                    state="disabled", bg=SURF, fg=MUTED,
                    activebackground=SURF, cursor=""
                )

        _update_revert_btn()
        _updaters.append(_update_revert_btn)

        btn_startup = _make_action_row(root,
            T("btn_startup"),
            T("btn_startup_desc"),
            O_BG,
            lambda: trigger_action(
                "restart_startup", T("confirm_startup_title"),
                T("confirm_startup_msg"),
                root=root
            )
        )

        def _update_startup_btn():
            if has_changes_to_revert():
                btn_startup.config(
                    state="normal", bg=O_BG, fg="white",
                    activebackground=O_BG, cursor="hand2"
                )
            else:
                btn_startup.config(
                    state="disabled", bg=SURF, fg=MUTED,
                    activebackground=SURF, cursor=""
                )

        _update_startup_btn()
        _updaters.append(_update_startup_btn)

        # Pasek statusu
        if is_admin():
            st_txt = T("status_admin")
            st_col = C_OK
        else:
            st_txt = T("status_user")
            st_col = C_WRN

        tk.Label(root, text=st_txt, font=("Segoe UI", 8),
                 fg=st_col, bg=BG3, anchor="w", padx=12, pady=4
                 ).pack(fill=tk.X, side=tk.BOTTOM)

    _build()
    root.deiconify()  # pokaż okno dopiero gdy UI jest w pełni zbudowane
    root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not is_windows():
        sys.exit(T("win_only"))

    if "--action" in sys.argv:
        idx = sys.argv.index("--action")
        if idx + 1 < len(sys.argv):
            run_action_mode(sys.argv[idx + 1])
    else:
        main()
