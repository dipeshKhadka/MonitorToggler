#Requires AutoHotkey v2.0
#SingleInstance Force

; ============================================================
;  MonitorToggler.ahk
;  Ctrl+Alt+R  :  Toggle between 4K@120Hz <-> QHD@240Hz (primary monitor)
;  Ctrl+Alt+O  :  Cycle orientation 90° clockwise (monitor under cursor)
;  Right-click tray icon for status and options.
; ============================================================

class DEVMODE {
    ; DEVMODEW field offsets and sizes
    static SIZE              := 220    ; total struct byte size
    static OFF_DMSIZE        := 68     ; WORD  — must be set to SIZE
    static OFF_FIELDS        := 72     ; DWORD — bitmask of valid fields
    static OFF_ORIENTATION   := 84     ; DWORD — dmDisplayOrientation
    static OFF_PELSWIDTH     := 172    ; DWORD — dmPelsWidth
    static OFF_PELSHEIGHT    := 176    ; DWORD — dmPelsHeight
    static OFF_FREQUENCY     := 184    ; DWORD — dmDisplayFrequency

    ; dmFields flag bits
    static DM_ORIENTATION    := 0x00000080
    static DM_PELSWIDTH      := 0x00080000
    static DM_PELSHEIGHT     := 0x00100000
    static DM_FREQUENCY      := 0x00400000
}

; Orientation index 0-3 maps to these labels (AHK arrays are 1-based so [or+1])
ORIENT_LABELS := ["Landscape (0°)", "Portrait (90°)", "Landscape Flipped (180°)", "Portrait Flipped (270°)"]

; ---- Tray setup ----
A_TrayMenu.Delete()
A_TrayMenu.Add("Status",         ShowStatus)
A_TrayMenu.Add()
A_TrayMenu.Add("Run at Startup", ToggleStartup)
A_TrayMenu.Add()
A_TrayMenu.Add("Exit",           (*) => ExitApp())
UpdateStartupCheck()
A_IconTip := "MonitorToggler`nCtrl+Alt+R  —  Toggle 4K@120 / QHD@240`nCtrl+Alt+O  —  Cycle orientation (cursor monitor)"

; ---- Hotkeys ----
^!r:: ToggleResolution()
^!o:: CycleOrientation()

; ============================================================
;  ToggleResolution — switches primary monitor between
;  3840x2160@120Hz and 2560x1440@240Hz
; ============================================================
ToggleResolution(*) {
    dm := ReadMode("")
    if !dm
        return

    w := NumGet(dm, DEVMODE.OFF_PELSWIDTH,  "UInt")
    h := NumGet(dm, DEVMODE.OFF_PELSHEIGHT, "UInt")

    if (w = 3840 && h = 2160) {
        nW := 2560, nH := 1440, nHz := 240
        lbl := "QHD  2560x1440  @  240 Hz"
    } else {
        nW := 3840, nH := 2160, nHz := 120
        lbl := "4K   3840x2160  @  120 Hz"
    }

    NumPut("UInt", DEVMODE.DM_PELSWIDTH | DEVMODE.DM_PELSHEIGHT | DEVMODE.DM_FREQUENCY, dm, DEVMODE.OFF_FIELDS)
    NumPut("UInt", nW,  dm, DEVMODE.OFF_PELSWIDTH)
    NumPut("UInt", nH,  dm, DEVMODE.OFF_PELSHEIGHT)
    NumPut("UInt", nHz, dm, DEVMODE.OFF_FREQUENCY)

    WriteMode("", dm, lbl)
}

; ============================================================
;  CycleOrientation — advances the monitor under the cursor
;  through 0° → 90° → 180° → 270° → 0° …
; ============================================================
CycleOrientation(*) {
    global ORIENT_LABELS

    idx     := MonitorAtCursor()
    devName := MonitorGetName(idx)

    dm := ReadMode(devName)
    if !dm
        return

    curOr := NumGet(dm, DEVMODE.OFF_ORIENTATION, "UInt")
    curW  := NumGet(dm, DEVMODE.OFF_PELSWIDTH,   "UInt")
    curH  := NumGet(dm, DEVMODE.OFF_PELSHEIGHT,  "UInt")

    newOr := Mod(curOr + 1, 4)

    ; Width and height must be swapped when crossing landscape<->portrait boundary
    ; Landscape indices: 0, 2  |  Portrait indices: 1, 3
    swapNeeded := (Mod(curOr, 2) != Mod(newOr, 2))
    nW := swapNeeded ? curH : curW
    nH := swapNeeded ? curW : curH

    NumPut("UInt", DEVMODE.DM_ORIENTATION | DEVMODE.DM_PELSWIDTH | DEVMODE.DM_PELSHEIGHT, dm, DEVMODE.OFF_FIELDS)
    NumPut("UInt", newOr, dm, DEVMODE.OFF_ORIENTATION)
    NumPut("UInt", nW,    dm, DEVMODE.OFF_PELSWIDTH)
    NumPut("UInt", nH,    dm, DEVMODE.OFF_PELSHEIGHT)

    WriteMode(devName, dm, "Monitor " idx "  ->  " ORIENT_LABELS[newOr + 1])
}

; ============================================================
;  Helpers
; ============================================================

ReadMode(devName) {
    dm := Buffer(DEVMODE.SIZE, 0)
    NumPut("UShort", DEVMODE.SIZE, dm, DEVMODE.OFF_DMSIZE)

    ok := devName
        ? DllCall("EnumDisplaySettingsW", "Str", devName, "UInt", 0xFFFFFFFF, "Ptr", dm)
        : DllCall("EnumDisplaySettingsW", "Ptr", 0,       "UInt", 0xFFFFFFFF, "Ptr", dm)

    if !ok {
        MsgBox "Could not read display settings.", "MonitorToggler", 16
        return 0
    }
    return dm
}

WriteMode(devName, dm, label) {
    ; CDS_UPDATEREGISTRY = 1  (persist setting across logins)
    rc := devName
        ? DllCall("ChangeDisplaySettingsExW", "Str", devName, "Ptr", dm, "Ptr", 0, "UInt", 1, "Ptr", 0)
        : DllCall("ChangeDisplaySettingsExW", "Ptr", 0,       "Ptr", dm, "Ptr", 0, "UInt", 1, "Ptr", 0)

    if rc >= 0  ; 0=success, 1=restart required (rare)
        TrayTip label, "MonitorToggler", 1
    else
        MsgBox "Display mode change failed (code " rc ").`nThe requested resolution or refresh rate may not be supported by your hardware.",
               "MonitorToggler", 16
}

MonitorAtCursor() {
    MouseGetPos(&mx, &my)
    Loop MonitorGetCount() {
        MonitorGet(A_Index, &L, &T, &R, &B)
        if (mx >= L && mx < R && my >= T && my < B)
            return A_Index
    }
    return MonitorGetPrimary()
}

; ---- Tray menu handlers ----

ShowStatus(*) {
    global ORIENT_LABELS
    dm := ReadMode("")
    if !dm
        return
    w  := NumGet(dm, DEVMODE.OFF_PELSWIDTH,   "UInt")
    h  := NumGet(dm, DEVMODE.OFF_PELSHEIGHT,  "UInt")
    hz := NumGet(dm, DEVMODE.OFF_FREQUENCY,   "UInt")
    or := NumGet(dm, DEVMODE.OFF_ORIENTATION, "UInt")
    MsgBox "Resolution:    " w " x " h "`nRefresh rate:  " hz " Hz`nOrientation:   " ORIENT_LABELS[or + 1],
           "Primary Monitor Status", 64
}

ToggleStartup(*) {
    lnk := A_Startup "\MonitorToggler.lnk"
    if FileExist(lnk) {
        FileDelete lnk
        A_TrayMenu.Uncheck("Run at Startup")
        TrayTip "Removed from Windows startup", "MonitorToggler", 1
    } else {
        FileCreateShortcut A_ScriptFullPath, lnk
        A_TrayMenu.Check("Run at Startup")
        TrayTip "Added to Windows startup", "MonitorToggler", 1
    }
}

UpdateStartupCheck() {
    if FileExist(A_Startup "\MonitorToggler.lnk")
        A_TrayMenu.Check("Run at Startup")
}
