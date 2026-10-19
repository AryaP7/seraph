"""C13 — OS-owned single-worker lock; released by the OS on crash.

Heartbeat age is diagnostic, not proof that a process has exited. This lock
prevents two workers (including one-off acquisition) writing the same store.
"""
from contextlib import contextmanager
from pathlib import Path
import os


class WorkerAlreadyRunning(RuntimeError):
    pass


def lock_path(store_path, name="worker") -> Path:
    return Path(str(Path(store_path).resolve()) + f".{name}.lock")


def lock_held(store_path, name="worker") -> bool:
    """Is somebody already holding this lock?

    A PROBE, not a claim: it takes the lock and immediately releases it,
    so the answer is only true at the instant it was asked. Callers use it
    to avoid spawning a process that would merely refuse to start; the
    lock itself, taken by that process, is what actually guarantees one
    owner. Treating this as the guarantee would be a race.
    """
    try:
        with worker_lock(store_path, name):
            return False
    except WorkerAlreadyRunning:
        return True
    except OSError:
        # The question could not be asked -- a missing directory, a
        # permission problem. Reporting "free" would invite a second
        # worker, so report held and let the caller say why it did not
        # start one.
        return True


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
