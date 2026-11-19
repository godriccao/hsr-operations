; Session configuration is local and never grants host input permission.
LoadSession(path) {
    if !FileExist(path)
        ExitApp 2
    gamePath := IniRead(path, "Session", "GamePath", "")
    expiresAt := IniRead(path, "Session", "ExpiresAt", "")
    runtimeDir := IniRead(path, "Session", "RuntimeDir", "")
    if !RegExMatch(gamePath, "i)^(?:[a-z]:\\|\\\\).+\\StarRail\.exe$") || !FileExist(gamePath)
        ExitApp 2
    if !RegExMatch(expiresAt, "^\d{14}$") || A_Now >= expiresAt
        ExitApp 2
    try DateDiff(expiresAt, A_Now, "Seconds")
    catch
        ExitApp 2
    if !RegExMatch(runtimeDir, "i)^(?:[a-z]:\\|\\\\).+")
        ExitApp 2
    DirCreate runtimeDir
    return {GamePath: gamePath, ExpiresAt: expiresAt, RuntimeDir: runtimeDir}
}
