#Requires AutoHotkey v2.0
#SingleInstance Ignore
#Include session-config.ahk
if A_Args.Length != 3
    ExitApp 2
config := LoadSession(A_Args[1])
h := WinActive('ahk_exe StarRail.exe')
if !h || WinGetProcessPath(h) != config.GamePath
    ExitApp 3
x := Max(-2400, Min(2400, Integer(A_Args[2])))
y := Max(-2400, Min(2400, Integer(A_Args[3])))
DllCall('mouse_event', 'UInt', 1, 'Int', x, 'Int', y, 'UInt', 0, 'UPtr', 0)
