# MonitorToggler

A lightweight Windows background utility to switch monitor resolution presets and cycle screen orientation using global keyboard shortcuts.

Runs silently in the system tray with no console window. Safe to use alongside games — it uses native Windows APIs only (no hook injection, no AutoHotkey process).

---

## Features

- **Resolution preset picker** — press a hotkey to open a popup for the monitor under your cursor. Pick from saved presets or define your own (any resolution + refresh rate). The active preset is highlighted.
- **Orientation cycling** — cycles the monitor under your cursor through 0° → 90° → 180° → 270° → 0° with a single keypress.
- **Fully configurable hotkeys** — change any shortcut from the tray menu, no config file editing needed.
- **Per-preset management** — add, edit, delete presets at any time. Saved to `%APPDATA%\MonitorToggler\config.json`.
- **Run at startup** — optional Windows startup entry via the tray menu.

---

## Default hotkeys

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Shift + R` | Open resolution preset picker (monitor under cursor) |
| `Ctrl + Alt + Shift + O` | Cycle orientation 90° clockwise (monitor under cursor) |

Both hotkeys are fully rebindable via **tray icon → Hotkey Settings**.

---

## Usage

### Option A — Download the exe (no Python needed)

Download `MonitorToggler.exe` from [Releases](../../releases) and run it. A monitor icon will appear in the system tray.

### Option B — Run from source

**Requirements:** Python 3.10+

```
pip install -r requirements.txt
python MonitorToggler.py
```

### Option C — Build the exe yourself

```
build_MonitorToggler.bat
```

Output: `dist\MonitorToggler.exe`

---

## Tray menu

| Item | Action |
|---|---|
| Status | Shows current resolution, refresh rate, and orientation |
| Hotkey Settings | Change keyboard shortcuts, with key capture UI |
| Run at Startup | Toggle Windows startup entry |
| Exit | Close the app |

---

## Anti-cheat safety

The compiled exe is a plain Windows process with no AutoHotkey runtime, no DLL injection, and no keyboard hooks. It uses `RegisterHotKey` (the same API Windows itself uses for system shortcuts) and `ChangeDisplaySettingsEx` (a standard display API). No known anti-cheat flags this.

---

## License

MIT
