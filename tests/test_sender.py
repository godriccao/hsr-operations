import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bridge_sender import send_batch


@unittest.skipUnless(os.name == 'nt', 'Windows file semantics')
class SenderContract(unittest.TestCase):
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
