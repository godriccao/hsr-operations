"""Wait for an existing Windows process to gain focus without activating it."""

import argparse
import ctypes
from ctypes import wintypes


EVENT_SYSTEM_FOREGROUND = 3
WM_TIMER = 0x0113
WINEVENT_OUTOFCONTEXT = 0


def wait_foreground(target_pid, timeout_ms):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
        wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
    )
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.SetWinEventHook.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, callback_type,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    ]
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    user32.SetTimer.argtypes = [wintypes.HWND, wintypes.WPARAM, wintypes.UINT, ctypes.c_void_p]
    user32.SetTimer.restype = wintypes.WPARAM
    user32.KillTimer.argtypes = [wintypes.HWND, wintypes.WPARAM]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM

    def is_foreground():
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
        return pid.value == target_pid

    matched = False

    @callback_type
    def on_foreground(_hook, _event, _window, _object, _child, _thread, _when):
        nonlocal matched
        if is_foreground():
            matched = True
            user32.PostQuitMessage(0)

    hook = user32.SetWinEventHook(
        EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
        on_foreground, target_pid, 0, WINEVENT_OUTOFCONTEXT,
    )
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    timer = 0
    try:
        if is_foreground():
            return True
        timer = user32.SetTimer(None, 0, timeout_ms, None)
        if not timer:
            raise ctypes.WinError(ctypes.get_last_error())
        message = wintypes.MSG()
        while True:
            received = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if received == -1:
                raise ctypes.WinError(ctypes.get_last_error())
            if received == 0 or (message.message == WM_TIMER and message.wParam == timer):
                return matched or is_foreground()
            user32.DispatchMessageW(ctypes.byref(message))
    finally:
        if timer:
            user32.KillTimer(None, timer)
        user32.UnhookWinEvent(hook)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    args = parser.parse_args()
    if not 0 < args.pid <= 0xFFFFFFFF or not 0 < args.timeout_ms <= 0x7FFFFFFF:
        parser.error("PID and timeout must be positive Windows values")
    ready = wait_foreground(args.pid, args.timeout_ms)
    print("foreground" if ready else "timeout", flush=True)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
