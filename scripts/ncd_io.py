r"""ncd_io.py -- share-delete file access for NinjaTrader's live .ncd DB files.

WHY: on Windows a plain open(path, 'rb') (and shutil.copy2) opens WITHOUT
FILE_SHARE_DELETE, so while any of our scripts has an NT .ncd file open, NT
CANNOT delete it. A "Reload All Historical Data" deletes + re-downloads today's
live minute/tick file; if we're holding it, NT's delete throws an unhandled
IOException ("...being used by another process") and the PLATFORM CRASHES.

Opening with FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE lets NT
delete/rename the file out from under us at any time (our read just ends), so a
reload can never be blocked by (and thus crash because of) our processes.

Use open_shared(path) / read_bytes(path) instead of open()/Path.read_bytes,
and copy2(src, dst) instead of shutil.copy2, for ANY file under
Documents\NinjaTrader 8\db\ .
"""
from __future__ import annotations

import os
import sys
import shutil

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    import msvcrt

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _k32.CreateFileW
    _CreateFileW.restype = wintypes.HANDLE
    _CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]

    _GENERIC_READ = 0x80000000
    _SHARE_ALL = 0x1 | 0x2 | 0x4          # READ | WRITE | DELETE  <-- the point
    _OPEN_EXISTING = 3
    _FLAG_BACKUP_SEMANTICS = 0x02000000   # lets us also open directories if needed
    _INVALID = ctypes.c_void_p(-1).value

    def open_shared(path, mode: str = "rb"):
        """Open `path` read-only with full sharing incl. delete. Returns a normal
        Python file object (binary). NT can delete/rename the file while it's open."""
        h = _CreateFileW(str(path), _GENERIC_READ, _SHARE_ALL, None,
                         _OPEN_EXISTING, _FLAG_BACKUP_SEMANTICS, None)
        if not h or h == _INVALID:
            err = ctypes.get_last_error()
            raise OSError(err, f"CreateFileW failed ({err}) for {path}")
        try:
            fd = msvcrt.open_osfhandle(int(h), os.O_RDONLY)
        except Exception:
            _k32.CloseHandle(ctypes.c_void_p(h))
            raise
        # os.fdopen owns the fd (and thus the handle) now.
        return os.fdopen(fd, "rb" if "b" in mode else "r")
else:  # non-Windows: plain open is fine (POSIX unlink works on open files)
    def open_shared(path, mode: str = "rb"):
        return open(path, mode)


def read_bytes(path) -> bytes:
    with open_shared(path, "rb") as f:
        return f.read()


def copy2(src, dst):
    """shutil.copy2 replacement: reads `src` with share-delete so NT can delete it
    mid-copy without crashing. If dst is a dir, copies into it. Preserves mtime."""
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(str(src)))
    with open_shared(src, "rb") as fsrc, open(dst, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst, length=1 << 20)
    try:
        shutil.copystat(src, dst)
    except Exception:
        pass
    return dst
