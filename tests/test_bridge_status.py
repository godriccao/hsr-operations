import ctypes
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path


BRIDGE = Path(__file__).resolve().parents[1] / "tools" / "bridge.ahk"


@unittest.skipUnless(os.name == "nt", "Windows file sharing semantics")
class BridgeStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        installed = Path(os.environ["ProgramFiles"]) / "AutoHotkey/v2/AutoHotkey64.exe"
        cls.ahk = shutil.which("AutoHotkey64.exe") or installed
        if not Path(cls.ahk).is_file():
            raise unittest.SkipTest("AutoHotkey v2 is required for bridge status tests")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        cls.open_file = kernel.CreateFileW
        cls.open_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        cls.open_file.restype = wintypes.HANDLE
        cls.close_handle = kernel.CloseHandle
        cls.close_handle.argtypes = (wintypes.HANDLE,)
        cls.close_handle.restype = wintypes.BOOL
        cls.source = BRIDGE.read_text(encoding="utf-8")
        status_start = cls.source.index("WriteStatus(line) {")
        cls.write_status = cls.source[status_start:cls.source.index("\n}\n", status_start) + 3]

    def start(self, script):
        return subprocess.Popen(
            [str(self.ahk), "/ErrorStdOut=UTF-8", str(script)],
            cwd=script.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def lock(self, status):
        # An open reader with share mode 0 blocks the bridge's FileAppend.
        handle = self.open_file(str(status), 0x80000000, 0, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def test_transient_lock_writes_one_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.log"
            status.touch()
            marker = root / "started.txt"
            script = root / "probe.ahk"
            script.write_text(
                "#Requires AutoHotkey v2.0\nSetWorkingDir A_ScriptDir\n"
                "FileAppend 'started', 'started.txt'\n"
                "WriteStatus 'ACK keys|W|80`n'\nExitApp()\n"
                + self.write_status,
                encoding="utf-8",
            )
            lock = self.lock(status)
            try:
                with self.start(script) as probe:
                    try:
                        deadline = time.monotonic() + 3
                        while not marker.exists() and time.monotonic() < deadline:
                            time.sleep(0.003)
                        self.assertTrue(marker.exists())
                        time.sleep(0.025)
                        self.close_handle(lock)
                        lock = None
                        output = probe.communicate(timeout=3)
                        self.assertEqual(probe.returncode, 0, output)
                    finally:
                        if probe.poll() is None:
                            probe.kill()
            finally:
                if lock is not None:
                    self.close_handle(lock)
            self.assertEqual(status.read_text(encoding="utf-8"), "ACK keys|W|80\n")
            self.assertFalse((root / "command.txt").exists())
            self.assertFalse((root / "claimed-command.txt").exists())

    def test_persistent_lock_exits_after_consuming_ping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.log"
            status.touch()
            command = root / "command.txt"
            command.write_bytes(b"ping")
            script = root / "probe.ahk"
            script.write_text(
                "#Requires AutoHotkey v2.0\nSetWorkingDir A_ScriptDir\n"
                "config := {ExpiresAt: DateAdd(A_Now, 1, 'Hours')}\n"
                "Poll()\nExitApp()\n"
                + self.write_status
                + self.source[self.source.index("ReleaseAll(*) {"):],
                encoding="utf-8",
            )
            lock = self.lock(status)
            try:
                with self.start(script) as probe:
                    try:
                        output = probe.communicate(timeout=3)
                        self.assertEqual(probe.returncode, 32, output)
                    finally:
                        if probe.poll() is None:
                            probe.kill()
            finally:
                self.close_handle(lock)
            self.assertEqual(status.read_bytes(), b"")
            self.assertFalse(command.exists())
            self.assertFalse((root / "claimed-command.txt").exists())
