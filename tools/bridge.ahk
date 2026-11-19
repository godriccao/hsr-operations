#Requires AutoHotkey v2.0
#SingleInstance Ignore
#Include session-config.ahk
Persistent
if A_Args.Length != 1
 ExitApp(2)
config := LoadSession(A_Args[1])
SetWorkingDir config.RuntimeDir
if FileExist('command.txt') || FileExist('claimed-command.txt')
 ExitApp(13)
SetKeyDelay 10, 40
CoordMode 'Mouse', 'Client'
started := A_TickCount
held := []
OnExit ReleaseAll
^!F12::ExitApp()
if !A_IsAdmin
 ExitApp(12)
WriteStatus 'READY ' A_Now '`n'
SetTimer Poll, 50
WriteStatus(line) {
 for delay in [0, 15, 30, 60] {
  if delay
   Sleep delay
  try {
   FileAppend line, 'status.log'
   return
  } catch OSError as err {
   if err.Number != 32 && err.Number != 33
    ExitApp(err.Number)
  }
 }
 ExitApp(32)
}
ReleaseAll(*) {
 global held
 for k in held
  SendEvent '{' k ' up}'
 held := []
}
Poll() {
 global started, held, config
 if A_Now >= config.ExpiresAt
  ExitApp()
 if !FileExist('command.txt')
  return
 try {
  if DateDiff(A_Now, FileGetTime('command.txt','M'), 'Seconds') > 30 {
   FileMove 'command.txt', 'expired-command.txt', 1
   return
  }
  FileMove 'command.txt', 'claimed-command.txt', 1
 } catch {
  return
 }
 try {
  cmd := FileRead('claimed-command.txt')
  FileDelete 'claimed-command.txt'
 } catch {
  return
 }
 if Trim(cmd) = 'ping' {
  WriteStatus 'PONG ' A_Now '`n'
  return
 }
 p := StrSplit(Trim(cmd, " `t`r`n"), '|')
 if p[1] = 'stop'
  ExitApp()
 if !WinActive('ahk_exe StarRail.exe') {
  WriteStatus 'FOCUS_REQUIRED`n'
  return
 }
 hwnd := WinActive('A')
 if WinGetProcessPath('ahk_id ' hwnd) != config.GamePath
  return
 if p.Length != 3
  return
 duration := Min(1000, Max(40, Integer(p[3])))
 if p[1] = 'keys' {
  keys := StrSplit(p[2], '+')
  for k in keys
   if !RegExMatch(k, 'i)^(?:[a-z0-9]|Space|Enter|Escape|Tab|Up|Down|Left|Right|LShift|LCtrl|F[1-9]|F1[0-2])$')
    return
  held := keys
  try {
   for k in keys
    SendEvent '{' k ' down}'
   deadline :=  A_TickCount+duration
   while A_TickCount<deadline {
    if !WinActive('ahk_id ' hwnd)
     break
    Sleep 10
   }
  } finally ReleaseAll()
 } else if p[1] = 'click' {
  xy := StrSplit(p[2], ',')
  if xy.Length != 2
   return
  WinGetClientPos ,,&w,&h,'ahk_id ' hwnd
  x := Integer(xy[1]), y := Integer(xy[2])
  if x<0 || y<0 || x>=w || y>=h
   return
  Click x,y
 } else
  return
 WriteStatus 'ACK ' cmd '`n'
}
