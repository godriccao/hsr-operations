#Requires AutoHotkey v2.0
#SingleInstance Ignore
#Include session-config.ahk
CoordMode "Pixel", "Screen"
^!F12::ExitApp()
SetKeyDelay 0
if A_Args.Length < 4 || A_Args.Length > 5 || A_Args[1] != "--live"
    ExitApp 2
centerX := Integer(A_Args[2])
centerY := Integer(A_Args[3])
config := LoadSession(A_Args[A_Args.Length])
windowsRemaining := A_Args.Length = 5 ? Integer(A_Args[4]) : 3
if (windowsRemaining < 1 || windowsRemaining > 3)
    ExitApp 2
gameWindow := WinActive("ahk_exe StarRail.exe")
if !gameWindow || WinGetProcessPath(gameWindow) != config.GamePath
    ExitApp 3
WinGetClientPos &left, &top, &width, &height, gameWindow
if (centerX < 10 || centerX + 10 >= width || centerY < 2 || centerY + 2 >= height)
    ExitApp 4
if CyanScore(left + centerX, top + centerY) >= 15
    ExitApp 5

startedAt := A_TickCount
lastEdge := startedAt
edgeCount := 0
cueTimes := []
consecutive := 0
previouslyDark := true
phaseEnd := 0
exitCode := 6
pressed := false
OnExit ReleaseHeld
try {
    SendEvent "{Space down}"
    pressed := true
    while A_TickCount - startedAt < 12000 {
        if !SameGameFrame() {
            exitCode := 7
            break
        }
        now := A_TickCount
        cyan := CyanScore(left + centerX, top + centerY) >= 15
        if edgeCount = windowsRemaining {
            if !cyan || now >= phaseEnd {
                exitCode := 0
                break
            }
        } else if (now - lastEdge > 5200) {
            break
        } else if !cyan {
            previouslyDark := true
            consecutive := 0
        } else if previouslyDark {
            consecutive += 1
            if consecutive >= 2 {
                ReleaseHeld()
                edgeCount += 1
                cueTimes.Push(now - startedAt)
                lastEdge := now
                previouslyDark := false
                consecutive := 0
                Sleep 70
                if !SameGameFrame() {
                    exitCode := 7
                    break
                }
                SendEvent "{Space down}"
                pressed := true
                phaseEnd := A_TickCount + 950
            }
        }
        Sleep 18
    }
} finally ReleaseHeld()
receipt := Format("edges={1} exit={2}`n", edgeCount, exitCode)
for index, elapsedMs in cueTimes
    receipt .= Format("cue={1} elapsed_ms={2}`n", index, elapsedMs)
try FileAppend receipt, config.RuntimeDir "\result-" A_Now "-" startedAt ".txt", "UTF-8"
ExitApp exitCode

SameGameFrame() {
    global gameWindow, left, top, width, height, config
    if A_Now >= config.ExpiresAt
        return false
    if !WinActive("ahk_id " gameWindow)
        return false
    WinGetClientPos &liveLeft, &liveTop, &liveWidth, &liveHeight, gameWindow
    return liveLeft = left && liveTop = top && liveWidth = width && liveHeight = height
}

ReleaseHeld(*) {
    global pressed
    if pressed {
        pressed := false
        SendEvent "{Space up}"
    }
}

CyanScore(x, y) {
    score := 0
    for dy in [-2, 0, 2] {
        for dx in [-10, -6, -2, 2, 6, 10] {
            color := PixelGetColor(x + dx, y + dy)
            red := (color >> 16) & 255
            green := (color >> 8) & 255
            blue := color & 255
            if (green >= 95 && blue >= 80 && 10 * red <= 7 * green && 10 * blue >= 6 * green)
                score += 1
        }
    }
    return score
}
