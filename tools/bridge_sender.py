"""Single-slot Windows sender library. Host must supply real control/foreground checks.

No live CLI and no default permission provider. Use only in a host that permits this
input channel. This library does not implement or bypass the host's control lease.
"""
import ctypes
import os
import re
import time
import uuid
from ctypes import wintypes
from pathlib import Path

KEY = r'(?:[a-z0-9]|Space|Enter|Escape|Tab|Up|Down|Left|Right|LShift|LCtrl|F[1-9]|F1[0-2])'
KEYS = re.compile(rf'keys\|{KEY}(?:\+{KEY})*\|\d+', re.I)
CLICK = re.compile(r'click\|\d+,\d+\|\d+')


if os.name == 'nt':
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.SetFilePointerEx.argtypes = (
        wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD,
    )
    kernel32.SetFilePointerEx.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = (
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    )
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL


def _read_status_tail(log, offset):
    # Python open() reports EACCES for both access denial and sharing conflicts.
    # Win32 calls preserve the specific error from opening or reading the file.
    generic_read = 0x80000000
    share_read_write = 3
    open_existing = 3
    handle = kernel32.CreateFileW(str(log), generic_read, share_read_write, None, open_existing, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel32.SetFilePointerEx(handle, offset, None, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(8192)
        size = wintypes.DWORD()
        tail = bytearray()
        while True:
            if not kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(size), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not size.value:
                return tail.decode('utf-8', errors='replace').replace('\r\n', '\n')
            tail.extend(buffer[:size.value])
    finally:
        kernel32.CloseHandle(handle)


def send_batch(runtime_dir, commands, *, control_status, foreground_ok, authorized,
               timeout=2.5, clock=time.monotonic, sleep=time.sleep, dispatch_interval_ms=None,
               receipt_sink=None):
    """Callbacks query the actual host each time; never replace them with cached ready.

    Returns relative dispatch/ack times. Any uncertainty raises and stops remaining
    commands. Existing pending files are preserved. No timeout retries.
    An optional empty list retains this batch's recorded events even on failure.
    An optional (minimum, maximum) interval in integer milliseconds applies between
    successive publications in a batch of Space jumps. After each ACK, any remaining
    minimum wait precedes fresh host and foreground checks for the next publication.
    """
    if os.name != 'nt':
        raise RuntimeError('Windows single-slot rename semantics required')
    if not authorized:
        raise PermissionError('current session has not authorized this input channel')
    if receipt_sink is not None and (type(receipt_sink) is not list or receipt_sink):
        raise ValueError('receipt sink must be an empty list')
    commands = list(commands)
    if not 1 <= len(commands) <= 12 or not 0 < timeout <= 10:
        raise ValueError('invalid batch size / timeout')
    for command in commands:
        if command not in ('ping', 'stop') and not (KEYS.fullmatch(command) or CLICK.fullmatch(command)):
            raise ValueError('unsupported command')
    if dispatch_interval_ms is not None:
        if (not isinstance(dispatch_interval_ms, (tuple, list)) or len(dispatch_interval_ms) != 2
                or any(type(bound) is not int for bound in dispatch_interval_ms)
                or not 1 <= dispatch_interval_ms[0] <= dispatch_interval_ms[1] <= 10_000):
            raise ValueError('dispatch interval must contain ordered integer bounds in 1..10000 ms')
        if len(commands) < 2 or any(
            not KEYS.fullmatch(command) or 'space' not in command.casefold().split('|')[1].split('+')
            for command in commands
        ):
            raise ValueError('dispatch interval requires at least two Space jumps')
        min_interval, max_interval = (bound / 1000 for bound in dispatch_interval_ms)
    root = Path(runtime_dir).resolve(strict=True)
    lock = root / 'sender.lock'
    # Exclusive lock refuses a second sender; a stale lock requires investigation.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    receipts = [] if receipt_sink is None else receipt_sink
    previous_dispatch = None
    origin = clock()
    try:
        for command in commands:
            latest_dispatch = None
            if dispatch_interval_ms is not None and previous_dispatch is not None:
                earliest_dispatch = previous_dispatch + min_interval
                latest_dispatch = previous_dispatch + max_interval
                now = clock()
                while now < earliest_dispatch:
                    sleep(earliest_dispatch - now)
                    now = clock()
                if now > latest_dispatch:
                    raise TimeoutError('dispatch interval expired before checking the next command')
            if control_status() != 'ready' or not foreground_ok():
                raise PermissionError('host not ready or game not foreground')
            if any((root / name).exists() for name in ('command.txt', 'claimed-command.txt')):
                raise RuntimeError('single slot occupied; inspect existing command')
            log = root / 'status.log'
            offset = log.stat().st_size if log.exists() else 0
            temporary = root / ('.pending-' + uuid.uuid4().hex)
            destination = root / 'command.txt'
            try:
                temporary.write_bytes(command.encode('utf-8'))
                if latest_dispatch is not None and clock() > latest_dispatch:
                    raise TimeoutError('dispatch interval expired while preparing the next command')
                # os.rename on Windows fails if destination exists; never overwrite.
                os.rename(temporary, destination)
                if dispatch_interval_ms is not None:
                    previous_dispatch = clock()
            finally:
                if temporary.exists():
                    temporary.unlink()
            dispatched = clock() if dispatch_interval_ms is None else previous_dispatch
            receipts.append({'type': 'dispatch', 't_ms': (dispatched-origin)*1000, 'command': command})
            if command == 'stop':
                break  # legacy protocol has no stop ACK
            deadline = clock() + timeout
            expected = 'PONG ' if command == 'ping' else 'ACK ' + command + '\n'
            while clock() < deadline:
                if control_status() != 'ready' or not foreground_ok():
                    raise PermissionError('control changed; stop and inspect pending / executed input')
                if clock() >= deadline:
                    continue
                try:
                    tail = _read_status_tail(log, offset)
                except OSError as error:
                    # The log may not exist yet. Sharing and range locks can clear
                    # before this command's deadline. The original offset stays fixed.
                    if getattr(error, 'winerror', None) not in (2, 32, 33):
                        raise
                    tail = ''
                observed = clock()
                if observed >= deadline:
                    continue
                if 'FOCUS_REQUIRED\n' in tail:
                    raise RuntimeError('focus required')
                pong = command == 'ping' and any(
                    re.fullmatch(r'PONG \d{14}\n', line) for line in tail.splitlines(keepends=True))
                if pong or (command != 'ping' and tail.endswith(expected)):
                    receipts.append({'type': 'ack', 't_ms': (observed-origin)*1000, 'command': command})
                    break
                sleep(min(0.05, deadline - observed))
            else:
                raise TimeoutError('ACK unknown; do not replay, inspect current game and slot')
            if latest_dispatch is not None and dispatched > latest_dispatch:
                # A rename that has already started can cross the deadline inside the OS.
                raise TimeoutError('command acknowledged, publication exceeded the dispatch interval; inspect game')
        return receipts
    finally:
        os.close(fd)
        lock.unlink()
