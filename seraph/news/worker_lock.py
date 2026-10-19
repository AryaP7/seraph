"""C13 — OS-owned single-worker lock; released by the OS on crash.

Heartbeat age is diagnostic, not proof that a process has exited. This lock
prevents two workers (including one-off acquisition) writing the same store.
"""
from contextlib import contextmanager
from pathlib import Path
import os


class WorkerAlreadyRunning(RuntimeError):
    pass


@contextmanager
def worker_lock(store_path, name="worker"):
    path = Path(str(Path(store_path).resolve()) + f".{name}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    acquired = False
    try:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise WorkerAlreadyRunning(f"a {name} already owns {store_path}") from exc
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()
