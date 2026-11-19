import ctypes
import os
import sys
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bridge_sender import send_batch


@unittest.skipUnless(os.name == 'nt', 'Windows file semantics')
class SenderContract(unittest.TestCase):
    def run_locked_ack(self, unlock_at=None, revoke_at=None, range_lock=None):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.LockFile.argtypes = (wintypes.HANDLE,) + (wintypes.DWORD,) * 4
        kernel.LockFile.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / 'status.log'
            previous_ack = b'ACK keys|W|80\n'
            status.write_bytes(previous_ack)  # Preexisting ACK cannot satisfy the new command.
            command_file = root / 'command.txt'
            consumed = []
            control_checks = []
            foreground_checks = []
            handle = None
            now = 0

            def control_status():
                control_checks.append(now)
                return 'user' if revoke_at is not None and now >= revoke_at else 'ready'

            def foreground_ok():
                foreground_checks.append(now)
                return True

            def tick(seconds):
                nonlocal handle, now
                if command_file.exists():
                    command = command_file.read_text()
                    consumed.append(command)
                    command_file.unlink()
                    with status.open('ab') as stream:
                        stream.write(('ACK ' + command + '\n').encode())
                    handle = kernel.CreateFileW(str(status), 0x80000000, 3 if range_lock else 0,
                                                None, 3, 0, None)
                    if handle == ctypes.c_void_p(-1).value:
                        handle = None
                        raise ctypes.WinError(ctypes.get_last_error())
                    if range_lock:
                        locked_offset = 0 if range_lock == 'previous' else len(previous_ack)
                        if not kernel.LockFile(handle, locked_offset, 0, 1, 0):
                            raise ctypes.WinError(ctypes.get_last_error())
                now += seconds
                if handle is not None and unlock_at is not None and now >= unlock_at:
                    kernel.CloseHandle(handle)
                    handle = None

            commands = ['keys|W|80']
            if unlock_at is None and range_lock != 'previous':
                commands.append('keys|D|80')
            try:
                result = send_batch(root, commands, control_status=control_status,
                                    foreground_ok=foreground_ok, authorized=True,
                                    timeout=0.25, clock=lambda: now, sleep=tick)
            except (OSError, TimeoutError) as error:
                result = error
            finally:
                if handle is not None:
                    kernel.CloseHandle(handle)
                self.assertFalse(command_file.exists())
                self.assertFalse((root / 'sender.lock').exists())
                self.assertEqual(consumed, ['keys|W|80'])
            return result, control_checks, foreground_checks, now

    def test_temporary_status_lock_recovers_original_ack(self):
        rows, control, foreground, elapsed = self.run_locked_ack(unlock_at=0.15)
        self.assertIsInstance(rows, list)
        self.assertEqual([row['type'] for row in rows], ['dispatch', 'ack'])
        self.assertGreater(len(control), 3)
        self.assertEqual(control, foreground)
        self.assertAlmostEqual(elapsed, 0.15)

    def test_status_byte_range_lock_recovers_original_ack(self):
        rows, control, foreground, elapsed = self.run_locked_ack(unlock_at=0.15, range_lock='new')
        self.assertIsInstance(rows, list)
        self.assertEqual([row['type'] for row in rows], ['dispatch', 'ack'])
        self.assertEqual(control, foreground)
        self.assertAlmostEqual(elapsed, 0.15)

    def test_read_starts_after_byte_range_lock_on_old_ack(self):
        rows, control, foreground, elapsed = self.run_locked_ack(range_lock='previous')
        self.assertIsInstance(rows, list)
        self.assertEqual([row['type'] for row in rows], ['dispatch', 'ack'])
        self.assertEqual(control, foreground)
        self.assertAlmostEqual(elapsed, 0.05)

    def test_access_denied_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = root / 'command.txt'
            consumed = []

            def tick(_):
                consumed.append(command.read_text())
                command.unlink()
                # Opening a directory as a file reports ERROR_ACCESS_DENIED.
                (root / 'status.log').mkdir()

            with self.assertRaises(PermissionError) as raised:
                send_batch(root, ['keys|W|80', 'keys|D|80'], control_status=lambda: 'ready',
                           foreground_ok=lambda: True, authorized=True, sleep=tick)
            self.assertEqual(raised.exception.winerror, 5)
            self.assertEqual(consumed, ['keys|W|80'])
            self.assertFalse(command.exists())
            self.assertFalse((root / 'sender.lock').exists())

    def test_persistent_status_lock_stops_at_original_deadline(self):
        error, control, foreground, elapsed = self.run_locked_ack()
        self.assertIsInstance(error, TimeoutError)
        self.assertIn('ACK unknown', str(error))
        self.assertEqual(control, foreground)
        self.assertAlmostEqual(elapsed, 0.25)

    def test_control_change_stops_during_status_lock(self):
        error, control, foreground, elapsed = self.run_locked_ack(revoke_at=0.10)
        self.assertIsInstance(error, PermissionError)
        self.assertIn('control changed', str(error))
        self.assertEqual(control[:-1], foreground)
        self.assertAlmostEqual(elapsed, 0.10)

    def test_slow_control_check_cannot_extend_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = root / 'command.txt'
            consumed = []
            now = 0

            def foreground_ok():
                nonlocal now
                if consumed:
                    now += 0.20
                return True

            def tick(seconds):
                nonlocal now
                consumed.append(command.read_text())
                command.unlink()
                (root / 'status.log').mkdir()  # A read here would fail with error 5.
                now += seconds

            with self.assertRaises(TimeoutError):
                send_batch(root, ['keys|W|80', 'keys|D|80'], control_status=lambda: 'ready',
                           foreground_ok=foreground_ok, authorized=True, timeout=0.25,
                           clock=lambda: now, sleep=tick)
            self.assertEqual(consumed, ['keys|W|80'])
            self.assertFalse(command.exists())

    def test_user_and_unauthorized_never_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            for authorized, state in [(False, 'ready'), (True, 'user'), (True, 'ai')]:
                with self.assertRaises(PermissionError):
                    send_batch(directory, ['keys|W|80'], control_status=lambda: state,
                               foreground_ok=lambda: True, authorized=authorized)
                self.assertFalse((Path(directory) / 'command.txt').exists())

    def test_pending_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            pending = Path(directory) / 'command.txt'
            pending.write_bytes(b'old-command')
            with self.assertRaises(RuntimeError):
                send_batch(directory, ['keys|W|80'], control_status=lambda: 'ready',
                           foreground_ok=lambda: True, authorized=True)
            self.assertEqual(pending.read_bytes(), b'old-command')

    def test_new_ack_required_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'status.log').write_bytes(b'ACK keys|W|80\n')
            with self.assertRaises(TimeoutError):
                send_batch(directory, ['keys|W|80', 'keys|D|80'], control_status=lambda: 'ready',
                           foreground_ok=lambda: True, authorized=True, timeout=0.01)
            self.assertEqual((Path(directory) / 'command.txt').read_bytes(), b'keys|W|80')

    def test_repeated_commands_new_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumed = []

            def simulator_sleep(_):
                command = root / 'command.txt'
                if command.exists():
                    value = command.read_text()
                    consumed.append(value)
                    command.unlink()
                    with (root / 'status.log').open('ab') as stream:
                        stream.write(('ACK ' + value + '\n').encode())

            rows = send_batch(directory, ['keys|W|80']*2, control_status=lambda: 'ready',
                              foreground_ok=lambda: True, authorized=True, sleep=simulator_sleep)
            self.assertEqual(consumed, ['keys|W|80']*2)
            self.assertEqual([r['type'] for r in rows], ['dispatch', 'ack', 'dispatch', 'ack'])


if __name__ == '__main__':
    unittest.main()
