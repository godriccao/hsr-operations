"""Single-slot Windows sender library. Host must supply real control/foreground checks.

No live CLI and no default permission provider. Use only in a host that permits this
input channel. This library does not implement or bypass the host's control lease.
"""
import os
import re
import time
import uuid
from pathlib import Path

KEY = r'(?:[a-z0-9]|Space|Enter|Escape|Tab|Up|Down|Left|Right|LShift|LCtrl|F[1-9]|F1[0-2])'
KEYS = re.compile(rf'keys\|{KEY}(?:\+{KEY})*\|\d+', re.I)
CLICK = re.compile(r'click\|\d+,\d+\|\d+')


def send_batch(runtime_dir, commands, *, control_status, foreground_ok, authorized,
               timeout=2.5, clock=time.monotonic, sleep=time.sleep):
    """Callbacks query the actual host each time; never replace them with cached ready.

    Returns relative dispatch/ack times. Any uncertainty raises and stops remaining
    commands. Existing pending files are preserved. No timeout retries.
    """
    if os.name != 'nt':
        raise RuntimeError('Windows single-slot rename semantics required')
    if not authorized:
        raise PermissionError('current session has not authorized this input channel')
    commands = list(commands)
    if not 1 <= len(commands) <= 12 or not 0 < timeout <= 10:
        raise ValueError('invalid batch size / timeout')
    for command in commands:
        if command not in ('ping', 'stop') and not (KEYS.fullmatch(command) or CLICK.fullmatch(command)):
            raise ValueError('unsupported command')
    root = Path(runtime_dir).resolve(strict=True)
    lock = root / 'sender.lock'
    # Exclusive lock refuses a second sender; a stale lock requires investigation.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    receipts = []
    origin = clock()
    try:
        for command in commands:
            if control_status() != 'ready' or not foreground_ok():
                raise PermissionError('host not ready or game not foreground')
            if any((root / name).exists() for name in ('command.txt', 'claimed-command.txt')):
                raise RuntimeError('single slot occupied; inspect existing command')
            log = root / 'status.log'
            offset = log.stat().st_size if log.exists() else 0
            temporary = root / ('.pending-' + uuid.uuid4().hex)
            try:
                temporary.write_bytes(command.encode('utf-8'))
                # os.rename on Windows fails if destination exists; never overwrite.
                os.rename(temporary, root / 'command.txt')
            finally:
                if temporary.exists():
                    temporary.unlink()
            receipts.append({'type': 'dispatch', 't_ms': (clock()-origin)*1000, 'command': command})
            if command == 'stop':
                break  # legacy protocol has no stop ACK
            deadline = clock() + timeout
            expected = 'PONG ' if command == 'ping' else 'ACK ' + command + '\n'
            while True:
                if control_status() != 'ready' or not foreground_ok():
                    raise PermissionError('control changed; stop and inspect pending / executed input')
                if log.exists():
                    with log.open('rb') as stream:
                        stream.seek(offset)
                        tail = stream.read().decode('utf-8', errors='replace').replace('\r\n', '\n')
                    if 'FOCUS_REQUIRED\n' in tail:
                        raise RuntimeError('focus required')
                    pong = command == 'ping' and any(
                        re.fullmatch(r'PONG \d{14}\n', line) for line in tail.splitlines(keepends=True))
                    if pong or (command != 'ping' and tail.endswith(expected)):
                        receipts.append({'type': 'ack', 't_ms': (clock()-origin)*1000, 'command': command})
                        break
                if clock() >= deadline:
                    raise TimeoutError('ACK unknown; do not replay, inspect current game and slot')
                sleep(0.05)
        return receipts
    finally:
        os.close(fd)
        lock.unlink()
