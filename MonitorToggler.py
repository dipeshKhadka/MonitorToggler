"""
MonitorToggler  —  background monitor settings tool
Default hotkeys:
  Ctrl+Alt+Shift+R  :  Open resolution preset picker  (monitor under cursor)
  Ctrl+Alt+Shift+O  :  Cycle orientation 90° clockwise (monitor under cursor)
Right-click tray icon -> Hotkey Settings to customise.
"""

import ctypes
import ctypes.wintypes as wt
import threading
import winreg
import sys
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
import tkinter as tk
from tkinter import ttk


# ── Win32 handles ──────────────────────────────────────────────────────────────
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


# ── DEVMODEW structure (220 bytes, Unicode) ────────────────────────────────────
class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",         wt.WCHAR * 32),
        ("dmSpecVersion",        wt.WORD),
        ("dmDriverVersion",      wt.WORD),
        ("dmSize",               wt.WORD),
        ("dmDriverExtra",        wt.WORD),
        ("dmFields",             wt.DWORD),
        ("dmPositionX",          wt.LONG),
        ("dmPositionY",          wt.LONG),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        ("dmColor",              ctypes.c_short),
        ("dmDuplex",             ctypes.c_short),
        ("dmYResolution",        ctypes.c_short),
        ("dmTTOption",           ctypes.c_short),
        ("dmCollate",            ctypes.c_short),
        ("dmFormName",           wt.WCHAR * 32),
        ("dmLogPixels",          wt.WORD),
        ("dmBitsPerPel",         wt.DWORD),
        ("dmPelsWidth",          wt.DWORD),
        ("dmPelsHeight",         wt.DWORD),
        ("dmDisplayFlags",       wt.DWORD),
        ("dmDisplayFrequency",   wt.DWORD),
        ("dmICMMethod",          wt.DWORD),
        ("dmICMIntent",          wt.DWORD),
        ("dmMediaType",          wt.DWORD),
        ("dmDitherType",         wt.DWORD),
        ("dmReserved1",          wt.DWORD),
        ("dmReserved2",          wt.DWORD),
        ("dmPanningWidth",       wt.DWORD),
        ("dmPanningHeight",      wt.DWORD),
    ]

assert ctypes.sizeof(DEVMODEW) == 220, f"DEVMODEW size={ctypes.sizeof(DEVMODEW)}"


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize",    wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork",    wt.RECT),
        ("dwFlags",   wt.DWORD),
        ("szDevice",  wt.WCHAR * 32),
    ]


# ── Win32 function signatures ──────────────────────────────────────────────────
user32.EnumDisplaySettingsW.restype  = wt.BOOL
user32.EnumDisplaySettingsW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(DEVMODEW)]

user32.ChangeDisplaySettingsExW.restype  = ctypes.c_long
user32.ChangeDisplaySettingsExW.argtypes = [
    wt.LPCWSTR, ctypes.POINTER(DEVMODEW), wt.HWND, wt.DWORD, ctypes.c_void_p,
]

user32.MonitorFromPoint.restype  = wt.HANDLE
user32.MonitorFromPoint.argtypes = [POINT, wt.DWORD]

user32.GetMonitorInfoW.restype  = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFOEXW)]

user32.RegisterHotKey.restype    = wt.BOOL
user32.RegisterHotKey.argtypes   = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]

user32.PostThreadMessageW.restype  = wt.BOOL
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]

kernel32.GetCurrentThreadId.restype = wt.DWORD


# ── Constants ──────────────────────────────────────────────────────────────────
DM_DISPLAYORIENTATION    = 0x00000080
DM_PELSWIDTH             = 0x00080000
DM_PELSHEIGHT            = 0x00100000
DM_DISPLAYFREQUENCY      = 0x00400000
ENUM_CURRENT_SETTINGS    = 0xFFFFFFFF
CDS_UPDATEREGISTRY       = 0x00000001
DISP_CHANGE_RESTART      = 1
MONITOR_DEFAULTTONEAREST = 2
WM_HOTKEY                = 0x0312
WM_QUIT                  = 0x0012
MOD_ALT                  = 0x0001
MOD_CONTROL              = 0x0002
MOD_SHIFT                = 0x0004
MOD_WIN                  = 0x0008
MOD_NOREPEAT             = 0x4000
HK_PRESETS               = 1
HK_CYCLE_ORI             = 2

ORIENT_LABELS = [
    "Landscape (0°)", "Portrait (90°)",
    "Landscape Flipped (180°)", "Portrait Flipped (270°)",
]

APP_NAME    = "MonitorToggler"
REG_RUN     = r"Software\Microsoft\Windows\CurrentVersion\Run"
CONFIG_DIR  = Path(os.environ.get("APPDATA", "~")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_PRESETS = [
    {"name": "4K @ 120 Hz",    "width": 3840, "height": 2160, "hz": 120},
    {"name": "QHD @ 240 Hz",   "width": 2560, "height": 1440, "hz": 240},
    {"name": "FHD @ 144 Hz",   "width": 1920, "height": 1080, "hz": 144},
    {"name": "FHD @ 60 Hz",    "width": 1920, "height": 1080, "hz":  60},
]

DEFAULT_CONFIG = {
    "presets":    DEFAULT_PRESETS,
    "preset_hk":  {"ctrl": True, "alt": True, "shift": True, "win": False, "key": "R"},
    "cycle_ori":  {"ctrl": True, "alt": True, "shift": True, "win": False, "key": "O"},
}

# ── Theme ──────────────────────────────────────────────────────────────────────
C_BG     = "#1e1e1e"
C_FG     = "#e0e0e0"
C_SUB    = "#888888"
C_ACCENT = "#0078d4"
C_ENTRY  = "#2d2d2d"
C_BTN    = "#3a3a3a"
C_BORDER = "#444444"
C_BLUE   = "#4fc3f7"
C_GREEN  = "#6bcb77"

# ── Globals ────────────────────────────────────────────────────────────────────
_icon               = None
_hotkey_tid         = None
_hotkey_done        = threading.Event()
_config             = {}
_config_lock        = threading.Lock()
_settings_open      = False
_preset_picker_open = False


# ── Config ─────────────────────────────────────────────────────────────────────

def _load_config():
    global _config
    try:
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        _config = {
            "presets":   saved.get("presets",   DEFAULT_PRESETS),
            "preset_hk": {**DEFAULT_CONFIG["preset_hk"], **saved.get("preset_hk", {})},
            "cycle_ori": {**DEFAULT_CONFIG["cycle_ori"],  **saved.get("cycle_ori",  {})},
        }
    except (FileNotFoundError, json.JSONDecodeError):
        _config = {k: (list(v) if isinstance(v, list) else dict(v))
                   for k, v in DEFAULT_CONFIG.items()}


def _save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(_config, f, indent=2)


# ── Hotkey helpers ─────────────────────────────────────────────────────────────

def _combo_to_win32(combo):
    mods = MOD_NOREPEAT
    if combo.get("ctrl"):  mods |= MOD_CONTROL
    if combo.get("alt"):   mods |= MOD_ALT
    if combo.get("shift"): mods |= MOD_SHIFT
    if combo.get("win"):   mods |= MOD_WIN
    return mods, _key_to_vk(combo.get("key", ""))


def _key_to_vk(key):
    key = key.upper()
    if len(key) == 1 and key.isalpha():  return ord(key)
    if len(key) == 1 and key.isdigit():  return ord(key)
    table = {
        **{f"F{i}": 0x6F + i for i in range(1, 13)},
        "SPACE": 0x20, "RETURN": 0x0D, "TAB": 0x09,
        "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
        "PRIOR": 0x21, "NEXT": 0x22,
        "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
        "MINUS": 0xBD, "EQUAL": 0xBB, "SEMICOLON": 0xBA,
        "COMMA": 0xBC, "PERIOD": 0xBE, "SLASH": 0xBF,
        "BRACKETLEFT": 0xDB, "BRACKETRIGHT": 0xDD,
        "BACKSLASH": 0xDC, "GRAVE": 0xC0, "APOSTROPHE": 0xDE,
    }
    return table.get(key, 0)


def _combo_to_str(combo):
    parts = []
    if combo.get("ctrl"):  parts.append("Ctrl")
    if combo.get("alt"):   parts.append("Alt")
    if combo.get("shift"): parts.append("Shift")
    if combo.get("win"):   parts.append("Win")
    parts.append(combo.get("key", "?"))
    return " + ".join(parts)


# ── Display functions ──────────────────────────────────────────────────────────

def _read_mode(device):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        _msgbox("Could not read display settings.")
        return None
    return dm


def _write_mode(device, dm, label):
    rc = user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None
    )
    if rc <= DISP_CHANGE_RESTART:
        _notify(label)
    else:
        _msgbox(f"Display mode change failed (code {rc}).\n"
                "The requested resolution or refresh rate may not be supported.")


def _apply_preset(device, preset):
    dm = _read_mode(device)
    if not dm:
        return
    dm.dmPelsWidth        = preset["width"]
    dm.dmPelsHeight       = preset["height"]
    dm.dmDisplayFrequency = preset["hz"]
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    _write_mode(device, dm,
                f"{preset['name']}  ({preset['width']}×{preset['height']} @ {preset['hz']} Hz)")


def cycle_orientation():
    device = _monitor_at_cursor()
    dm = _read_mode(device)
    if not dm:
        return
    cur = dm.dmDisplayOrientation
    new = (cur + 1) % 4
    if (cur % 2) != (new % 2):
        dm.dmPelsWidth, dm.dmPelsHeight = dm.dmPelsHeight, dm.dmPelsWidth
    dm.dmDisplayOrientation = new
    dm.dmFields = DM_DISPLAYORIENTATION | DM_PELSWIDTH | DM_PELSHEIGHT
    _write_mode(device, dm, ORIENT_LABELS[new])


# ── Monitor helpers ────────────────────────────────────────────────────────────

def _monitor_info_at_cursor():
    """Returns (device, left, top, right, bottom) for the monitor under the cursor."""
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        r = info.rcMonitor
        return info.szDevice, r.left, r.top, r.right, r.bottom
    return None


def _monitor_at_cursor():
    result = _monitor_info_at_cursor()
    return result[0] if result else None


# ── Notifications ──────────────────────────────────────────────────────────────

def _notify(msg):
    if _icon:
        try:
            _icon.notify(msg, APP_NAME)
        except Exception:
            pass


def _msgbox(msg, icon_flag=0x10):
    threading.Thread(
        target=lambda: user32.MessageBoxW(None, msg, APP_NAME, icon_flag | 0x00010000),
        daemon=True,
    ).start()


# ── Startup ────────────────────────────────────────────────────────────────────

def _exe_path():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def _in_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


def _set_startup(enable):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _exe_path())
            _notify("Added to Windows startup")
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
                _notify("Removed from Windows startup")
            except FileNotFoundError:
                pass


# ── Shared tkinter helpers ─────────────────────────────────────────────────────

def _apply_style(root):
    s = ttk.Style(root)
    s.theme_use("default")
    for name, bg, fg in [("TButton", C_BTN, C_FG), ("Accent.TButton", C_ACCENT, "white")]:
        s.configure(name, background=bg, foreground=fg,
                    relief="flat", borderwidth=0, padding=(10, 6), font=("Segoe UI", 9))
        hover = "#4a4a4a" if bg == C_BTN else "#006abc"
        s.map(name, background=[("active", hover), ("pressed", hover)])


def _dark_entry(parent, textvariable=None, width=16, readonly=False, font=None):
    kw = dict(bg=C_ENTRY, fg=C_FG, relief="flat",
              insertbackground=C_FG, font=font or ("Segoe UI", 9),
              width=width)
    if textvariable:
        kw["textvariable"] = textvariable
    if readonly:
        kw.update(state="readonly", readonlybackground=C_ENTRY, cursor="arrow")
    return tk.Entry(parent, **kw)


def _lbl(parent, text, fg=C_FG, size=9, bold=False, bg=C_BG):
    return tk.Label(parent, text=text, bg=bg, fg=fg,
                    font=("Segoe UI", size, "bold" if bold else "normal"))


def _sep(parent):
    return tk.Frame(parent, bg=C_BORDER, height=1)


# ── Preset picker window ───────────────────────────────────────────────────────

def show_preset_picker():
    global _preset_picker_open
    if _preset_picker_open:
        return
    info = _monitor_info_at_cursor()
    device, ml, mt, mr, mb = info if info else (None, 0, 0, 1920, 1080)
    threading.Thread(
        target=lambda: _preset_picker_window(device, ml, mt, mr, mb),
        daemon=True,
    ).start()


def _preset_picker_window(device, mon_l, mon_t, mon_r, mon_b):
    global _preset_picker_open
    _preset_picker_open = True
    try:
        dm     = _read_mode(device)
        cur_w  = dm.dmPelsWidth        if dm else 0
        cur_h  = dm.dmPelsHeight       if dm else 0
        cur_hz = dm.dmDisplayFrequency if dm else 0

        root = tk.Tk()
        root.title(f"{APP_NAME}  —  Resolution Presets")
        root.configure(bg=C_BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        _apply_style(root)

        W, H = 460, 350
        cx = mon_l + (mon_r - mon_l) // 2 - W // 2
        cy = mon_t + (mon_b - mon_t) // 2 - H // 2
        root.geometry(f"{W}x{H}+{cx}+{cy}")

        # Local editable copy of presets
        presets = [dict(p) for p in _config.get("presets", [])]

        # ── Header ──
        mon_label = (device or "Primary Monitor").replace("\\\\.\\", "")
        cur_str   = f"{cur_w} × {cur_h}  @  {cur_hz} Hz" if dm else "unknown"

        _lbl(root, "Resolution Presets", size=12, bold=True).pack(
            anchor="w", padx=20, pady=(16, 2))
        _lbl(root, f"  {mon_label}   ·   current: {cur_str}", fg=C_SUB).pack(
            anchor="w", padx=20)
        _sep(root).pack(fill="x", padx=20, pady=(8, 0))

        # ── Listbox ──
        lf = tk.Frame(root, bg=C_BG)
        lf.pack(fill="both", expand=True, padx=20, pady=(6, 0))

        sb = tk.Scrollbar(lf, bg=C_BTN, troughcolor=C_ENTRY,
                          activebackground=C_ACCENT, relief="flat", width=10)
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(
            lf, bg=C_ENTRY, fg=C_FG, font=("Consolas", 10),
            selectbackground=C_ACCENT, selectforeground="white",
            activestyle="none", relief="flat", highlightthickness=0,
            yscrollcommand=sb.set, cursor="hand2",
        )
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)

        def refresh_list(keep_sel=None):
            lb.delete(0, "end")
            for i, p in enumerate(presets):
                is_cur = (p["width"] == cur_w and p["height"] == cur_h and p["hz"] == cur_hz)
                mark   = "  ●" if is_cur else "   "
                line   = f"{mark}  {p['name']:<24}  {p['width']} × {p['height']}  @  {p['hz']} Hz"
                lb.insert("end", line)
                if is_cur:
                    lb.itemconfig(i, fg=C_GREEN)
            if keep_sel is not None and 0 <= keep_sel < len(presets):
                lb.selection_set(keep_sel)
                lb.see(keep_sel)

        refresh_list()

        # Pre-select the matching preset (if any)
        for i, p in enumerate(presets):
            if p["width"] == cur_w and p["height"] == cur_h and p["hz"] == cur_hz:
                lb.selection_set(i); lb.see(i); break

        # ── Preset management buttons (left side) ──
        _sep(root).pack(fill="x", padx=20, pady=(6, 0))

        bf = tk.Frame(root, bg=C_BG)
        bf.pack(fill="x", padx=20, pady=10)

        def selected_idx():
            s = lb.curselection()
            return s[0] if s else None

        def do_add():
            new_p = _preset_edit_dialog(root, {})
            if new_p:
                presets.append(new_p)
                refresh_list(keep_sel=len(presets) - 1)

        def do_edit():
            i = selected_idx()
            if i is None: return
            edited = _preset_edit_dialog(root, dict(presets[i]))
            if edited:
                presets[i] = edited
                refresh_list(keep_sel=i)

        def do_delete():
            i = selected_idx()
            if i is None: return
            presets.pop(i)
            refresh_list(keep_sel=min(i, len(presets) - 1) if presets else None)

        def do_apply():
            i = selected_idx()
            if i is None: return
            with _config_lock:
                _config["presets"] = presets
            _save_config()
            _apply_preset(device, presets[i])
            root.destroy()

        def do_close():
            with _config_lock:
                _config["presets"] = presets
            _save_config()
            root.destroy()

        ttk.Button(bf, text="Add",    command=do_add,    width=7).pack(side="left")
        ttk.Button(bf, text="Edit",   command=do_edit,   width=7).pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Delete", command=do_delete, width=7).pack(side="left", padx=(6, 0))

        ttk.Button(bf, text="Apply", command=do_apply,
                   style="Accent.TButton", width=8).pack(side="right")
        ttk.Button(bf, text="Close", command=do_close,
                   width=8).pack(side="right", padx=(0, 6))

        lb.bind("<Double-Button-1>", lambda _e: do_apply())
        root.bind("<Return>",        lambda _e: do_apply())
        root.bind("<Escape>",        lambda _e: do_close())
        root.protocol("WM_DELETE_WINDOW", do_close)
        root.mainloop()
    finally:
        _preset_picker_open = False


def _preset_edit_dialog(parent, preset_data):
    """Add / Edit preset. Returns new preset dict or None if cancelled."""
    result  = [None]
    is_new  = not preset_data

    dlg = tk.Toplevel(parent)
    dlg.title("Add Preset" if is_new else "Edit Preset")
    dlg.configure(bg=C_BG)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.grab_set()

    _apply_style(dlg)

    W2, H2 = 300, 230
    px = parent.winfo_x() + (parent.winfo_width()  - W2) // 2
    py = parent.winfo_y() + (parent.winfo_height() - H2) // 2
    dlg.geometry(f"{W2}x{H2}+{px}+{py}")

    _lbl(dlg, "Add Preset" if is_new else "Edit Preset",
         size=11, bold=True).grid(row=0, column=0, columnspan=2,
                                  sticky="w", padx=20, pady=(16, 10))

    name_v   = tk.StringVar(value=str(preset_data.get("name",   "")))
    width_v  = tk.StringVar(value=str(preset_data.get("width",  "")))
    height_v = tk.StringVar(value=str(preset_data.get("height", "")))
    hz_v     = tk.StringVar(value=str(preset_data.get("hz",     "")))
    err_v    = tk.StringVar()

    fields = [("Name", name_v), ("Width (px)", width_v),
              ("Height (px)", height_v), ("Refresh Hz", hz_v)]
    entries = []
    for row, (label, var) in enumerate(fields, start=1):
        _lbl(dlg, label, fg=C_SUB).grid(row=row, column=0, sticky="e", padx=(20, 6), pady=3)
        e = _dark_entry(dlg, textvariable=var, width=14)
        e.grid(row=row, column=1, sticky="w", padx=(0, 20), pady=3)
        entries.append(e)

    tk.Label(dlg, textvariable=err_v, bg=C_BG, fg="#ff6b6b",
             font=("Segoe UI", 8)).grid(row=5, column=0, columnspan=2, pady=(2, 0))

    def do_save():
        name = name_v.get().strip()
        if not name:
            err_v.set("Name is required."); return
        try:
            w  = int(width_v.get());  assert w  > 0
            h  = int(height_v.get()); assert h  > 0
            hz = int(hz_v.get());     assert hz > 0
        except (ValueError, AssertionError):
            err_v.set("Width / Height / Hz must be positive whole numbers."); return
        result[0] = {"name": name, "width": w, "height": h, "hz": hz}
        dlg.destroy()

    bf = tk.Frame(dlg, bg=C_BG)
    bf.grid(row=6, column=0, columnspan=2, pady=(6, 16))
    ttk.Button(bf, text="Cancel", command=dlg.destroy).pack(side="left", padx=(0, 8))
    ttk.Button(bf, text="Save", command=do_save,
               style="Accent.TButton", width=8).pack(side="left")

    entries[0].focus()
    dlg.bind("<Return>", lambda _e: do_save())
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    parent.wait_window(dlg)
    return result[0]


# ── Hotkey settings window ─────────────────────────────────────────────────────

def _open_settings(icon=None, item=None):
    global _settings_open
    if _settings_open:
        return
    threading.Thread(target=_settings_window, daemon=True).start()


def _settings_window():
    global _settings_open
    _settings_open = True
    try:
        root = tk.Tk()
        root.title(f"{APP_NAME}  —  Hotkey Settings")
        root.configure(bg=C_BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        _apply_style(root)

        W, H = 440, 220
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        res_combo = dict(_config["preset_hk"])
        ori_combo = dict(_config["cycle_ori"])
        res_var   = tk.StringVar(value=_combo_to_str(res_combo))
        ori_var   = tk.StringVar(value=_combo_to_str(ori_combo))

        _lbl(root, "Hotkey Settings", size=12, bold=True).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 4))
        _sep(root).grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 10))

        def make_row(grid_row, caption, var, combo_ref, dlg_title):
            _lbl(root, caption, fg=C_SUB).grid(
                row=grid_row, column=0, sticky="w", padx=(20, 0))
            e = _dark_entry(root, textvariable=var, width=26, readonly=True,
                            font=("Consolas", 10))
            e.config(fg=C_BLUE, readonlybackground=C_ENTRY)
            e.grid(row=grid_row, column=1, padx=(8, 6), pady=4, sticky="ew")

            def do_set(cr=combo_ref, v=var, t=dlg_title):
                new = _capture_dialog(root, dict(cr), t)
                if new is not None:
                    cr.clear(); cr.update(new); v.set(_combo_to_str(cr))

            ttk.Button(root, text="Set…", command=do_set, width=6).grid(
                row=grid_row, column=2, padx=(0, 20), pady=4)

        make_row(2, "Preset Picker  (open resolution presets)", res_var, res_combo,
                 "Set — Resolution Preset Hotkey")
        make_row(3, "Cycle Orientation  (cursor monitor)",       ori_var, ori_combo,
                 "Set — Cycle Orientation Hotkey")
        root.columnconfigure(1, weight=1)

        _sep(root).grid(row=4, column=0, columnspan=3, sticky="ew", padx=20, pady=(8, 0))

        bf = tk.Frame(root, bg=C_BG)
        bf.grid(row=5, column=0, columnspan=3, padx=20, pady=12, sticky="ew")

        def do_reset():
            res_combo.clear(); res_combo.update(DEFAULT_CONFIG["preset_hk"])
            ori_combo.clear(); ori_combo.update(DEFAULT_CONFIG["cycle_ori"])
            res_var.set(_combo_to_str(res_combo))
            ori_var.set(_combo_to_str(ori_combo))

        def do_save():
            with _config_lock:
                _config["preset_hk"] = dict(res_combo)
                _config["cycle_ori"] = dict(ori_combo)
            _save_config()
            _restart_hotkeys()
            _update_tray_tip()
            root.destroy()

        ttk.Button(bf, text="Reset to Defaults", command=do_reset).pack(side="left")
        ttk.Button(bf, text="Save", command=do_save,
                   style="Accent.TButton").pack(side="right")
        ttk.Button(bf, text="Cancel", command=root.destroy).pack(side="right", padx=(0, 6))

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    finally:
        _settings_open = False


def _capture_dialog(parent, current_combo, title):
    result    = [None]
    captured  = [dict(current_combo)]
    held_mods = set()
    MODIFIER_SYMS = {
        "Control_L","Control_R","Alt_L","Alt_R",
        "Shift_L","Shift_R","Super_L","Super_R","Meta_L","Meta_R",
    }

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=C_BG)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.grab_set()
    _apply_style(dlg)

    W2, H2 = 340, 190
    px = parent.winfo_x() + (parent.winfo_width()  - W2) // 2
    py = parent.winfo_y() + (parent.winfo_height() - H2) // 2
    dlg.geometry(f"{W2}x{H2}+{px}+{py}")

    _lbl(dlg, "Hold modifiers, then press a key:", fg=C_SUB).pack(pady=(20, 6))

    dv = tk.StringVar(value=_combo_to_str(current_combo))
    e  = _dark_entry(dlg, textvariable=dv, width=24, readonly=True,
                     font=("Consolas", 13, "bold"))
    e.config(fg=C_BLUE, readonlybackground=C_ENTRY, justify="center")
    e.pack(ipady=8, padx=30)

    wv = tk.StringVar()
    tk.Label(dlg, textvariable=wv, bg=C_BG, fg="#ff6b6b",
             font=("Segoe UI", 8)).pack(pady=(4, 0))

    def on_press(event):
        if event.keysym in MODIFIER_SYMS:
            held_mods.add(event.keysym); return
        ctrl  = any("Control" in m for m in held_mods)
        alt   = any("Alt" in m or "Meta" in m for m in held_mods)
        shift = any("Shift" in m for m in held_mods)
        win   = any("Super" in m for m in held_mods)
        key   = event.keysym.upper()
        if _key_to_vk(key) == 0:
            wv.set(f"'{event.keysym}' not supported — use A-Z, 0-9, F1-F12"); return
        if not any([ctrl, alt, shift, win]):
            wv.set("At least one modifier (Ctrl / Alt / Shift / Win) required"); return
        wv.set("")
        captured[0] = {"ctrl": ctrl, "alt": alt, "shift": shift, "win": win, "key": key}
        dv.set(_combo_to_str(captured[0]))

    def on_release(event): held_mods.discard(event.keysym)

    dlg.bind("<KeyPress>",   on_press)
    dlg.bind("<KeyRelease>", on_release)
    dlg.focus_force()

    bf = tk.Frame(dlg, bg=C_BG)
    bf.pack(pady=(10, 18))

    def do_set():
        result[0] = dict(captured[0]); dlg.destroy()

    ttk.Button(bf, text="Cancel", command=dlg.destroy).pack(side="left", padx=(0, 8))
    ttk.Button(bf, text="Set", command=do_set,
               style="Accent.TButton", width=7).pack(side="left")

    parent.wait_window(dlg)
    return result[0]


# ── Tray icon ──────────────────────────────────────────────────────────────────

def _make_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.rectangle([ 4,  6, 60, 46], fill=(24, 24, 24), outline=(180, 180, 180), width=3)
    d.rectangle([ 8, 10, 56, 42], fill=(0, 120, 215))
    d.rectangle([28, 46, 36, 54], fill=(180, 180, 180))
    d.rectangle([20, 54, 44, 58], fill=(180, 180, 180))
    return img


def _show_status(icon=None, item=None):
    dm = _read_mode(None)
    if not dm:
        return
    p_str = _combo_to_str(_config["preset_hk"])
    o_str = _combo_to_str(_config["cycle_ori"])
    _msgbox(
        f"Resolution:    {dm.dmPelsWidth} × {dm.dmPelsHeight}\n"
        f"Refresh rate:  {dm.dmDisplayFrequency} Hz\n"
        f"Orientation:   {ORIENT_LABELS[dm.dmDisplayOrientation]}\n\n"
        f"Preset picker hotkey:  {p_str}\n"
        f"Rotate hotkey:         {o_str}",
        icon_flag=0x40,
    )


def _build_menu():
    return pystray.Menu(
        pystray.MenuItem("Status",           _show_status),
        pystray.MenuItem("Hotkey Settings…", _open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Run at Startup",
            lambda icon, item: _set_startup(not _in_startup()),
            checked=lambda item: _in_startup(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", lambda icon, item: _quit(icon)),
    )


def _update_tray_tip():
    if _icon:
        p = _combo_to_str(_config["preset_hk"])
        o = _combo_to_str(_config["cycle_ori"])
        _icon.title = (f"{APP_NAME}\n"
                       f"{p}  —  Resolution preset picker\n"
                       f"{o}  —  Cycle orientation")


def _quit(icon):
    if _hotkey_tid:
        user32.PostThreadMessageW(_hotkey_tid, WM_QUIT, 0, 0)
    icon.stop()


# ── Hotkey thread ──────────────────────────────────────────────────────────────

def _hotkey_loop():
    global _hotkey_tid
    _hotkey_done.clear()
    _hotkey_tid = kernel32.GetCurrentThreadId()

    with _config_lock:
        p_mods, p_vk = _combo_to_win32(_config["preset_hk"])
        o_mods, o_vk = _combo_to_win32(_config["cycle_ori"])

    ok_p = user32.RegisterHotKey(None, HK_PRESETS,   p_mods, p_vk)
    ok_o = user32.RegisterHotKey(None, HK_CYCLE_ORI, o_mods, o_vk)

    if not ok_p or not ok_o:
        failed = []
        if not ok_p: failed.append(_combo_to_str(_config["preset_hk"]))
        if not ok_o: failed.append(_combo_to_str(_config["cycle_ori"]))
        _msgbox(
            "Could not register hotkey(s):\n" +
            "\n".join(f"  {f}" for f in failed) +
            "\n\nAnother app may be using them.\n"
            "Right-click the tray icon → Hotkey Settings to pick different ones."
        )

    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY:
            if   msg.wParam == HK_PRESETS:   show_preset_picker()
            elif msg.wParam == HK_CYCLE_ORI: cycle_orientation()
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    user32.UnregisterHotKey(None, HK_PRESETS)
    user32.UnregisterHotKey(None, HK_CYCLE_ORI)
    _hotkey_done.set()


def _restart_hotkeys():
    if _hotkey_tid:
        user32.PostThreadMessageW(_hotkey_tid, WM_QUIT, 0, 0)
        _hotkey_done.wait(timeout=2.0)
    threading.Thread(target=_hotkey_loop, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global _icon
    _load_config()
    threading.Thread(target=_hotkey_loop, daemon=True).start()
    _icon = pystray.Icon(APP_NAME, _make_icon_image(), APP_NAME, _build_menu())
    _update_tray_tip()
    _icon.run()


if __name__ == "__main__":
    main()
