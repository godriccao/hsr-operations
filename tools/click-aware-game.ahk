#Requires AutoHotkey v2.0
#SingleInstance Ignore
#Include session-config.ahk
if A_Args.Length != 3 && A_Args.Length != 5
    ExitApp 2
config := LoadSession(A_Args[1])
h := WinActive('ahk_exe StarRail.exe')
if !h || WinGetProcessPath(h) != config.GamePath
    ExitApp 3
DllCall('SetThreadDpiAwarenessContext', 'Ptr', -4, 'Ptr')
WinGetClientPos &left, &top, &width, &height, h
x := Round(Number(A_Args[2]) * width), y := Round(Number(A_Args[3]) * height)
tx := x, ty := y
if A_Args.Length = 5 {
    tx += Round(Number(A_Args[4]) * width)
    ty += Round(Number(A_Args[5]) * height)
}
if Min(x, tx) < 0 || Min(y, ty) < 0 || Max(x, tx) >= width || Max(y, ty) >= height
    ExitApp 4
pressed := false
OnExit ReleaseMouse
^!F12::ExitApp()
try {
    startX := left + x, startY := top + y
    if !DllCall('SetCursorPos', 'Int', startX, 'Int', startY, 'Int')
        ExitApp 8
    Sleep 120
    if !SameFrame()
        ExitApp 7
    if !CursorAt(startX, startY)
        ExitApp 8
    DllCall('mouse_event', 'UInt', 2, 'UInt', 0, 'UInt', 0, 'UInt', 0, 'UPtr', 0)
    pressed := true
    if A_Args.Length = 5 {
        Loop 20 {
            if !SameFrame()
                ExitApp 7
            stepX := left + Round(x + (tx - x) * A_Index / 20)
            stepY := top + Round(y + (ty - y) * A_Index / 20)
            if !DllCall('SetCursorPos', 'Int', stepX, 'Int', stepY, 'Int') || !CursorAt(stepX, stepY)
                ExitApp 8
            Sleep 20
        }
    }
    Sleep 80
} finally ReleaseMouse()
ExitApp()
CursorAt(x, y) {
    point := Buffer(8)
    return DllCall('GetCursorPos', 'Ptr', point, 'Int')
        && NumGet(point, 0, 'Int') = x && NumGet(point, 4, 'Int') = y
}
SameFrame() {
    global h, left, top, width, height, config
    if !WinActive('ahk_id ' h) || A_Now >= config.ExpiresAt
        return false
    WinGetClientPos &l, &t, &w, &ht, h
    return l = left && t = top && w = width && ht = height
}
ReleaseMouse(*) {
    global pressed
    if pressed {
        pressed := false
        DllCall('mouse_event', 'UInt', 4, 'UInt', 0, 'UInt', 0, 'UInt', 0, 'UPtr', 0)
    }
}
