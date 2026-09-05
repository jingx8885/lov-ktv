"""Single-worker lifecycle and duplicate suppression for background jobs."""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

JobFn = Callable[..., Any]


def _job_key(fn: JobFn, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    name = getattr(fn, "__name__", str(fn))
    song_id = args[0] if args else ""
    options = ",".join(f"{key}={kwargs[key]!r}" for key in sorted(kwargs))
    return f"{name}:{song_id}:{options}"


class JobQueue:
    """Small single-worker queue with duplicate suppression."""

    def __init__(self, worker_name: str = "lovktv-jobs") -> None:
        self._jobs: queue.Queue[tuple[JobFn, tuple[Any, ...], dict[str, Any], str]] = (
            queue.Queue()
        )
        self._queued: set[str] = set()
        self._lock = threading.Lock()
        self._worker_started = False
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._worker_name = worker_name

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                fn, args, kwargs, key = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                print(f"[lovktv] start {key}", flush=True)
                fn(*args, **kwargs)
                print(f"[lovktv] done {key}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[lovktv] fail {key}: {exc}", flush=True)
            finally:
                with self._lock:
                    self._queued.discard(key)
                self._jobs.task_done()
        with self._lock:
            self._worker_started = False
            self._worker_thread = None

    def start(self) -> bool:
        with self._lock:
            if (
                self._worker_started
                and self._worker_thread
                and self._worker_thread.is_alive()
            ):
                return False
            self._stop_event.clear()
            self._worker_started = True
            self._worker_thread = threading.Thread(
                target=self._worker, name=self._worker_name, daemon=True
            )
            self._worker_thread.start()
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        with self._lock:
            thread = self._worker_thread
            if not self._worker_started or thread is None:
                return False
            self._stop_event.set()
        thread.join(max(0.0, timeout))
        if thread.is_alive():
            return False
        while True:
            try:
                _fn, _args, _kwargs, key = self._jobs.get_nowait()
            except queue.Empty:
                break
            with self._lock:
                self._queued.discard(key)
            self._jobs.task_done()
        with self._lock:
            self._worker_started = False
            self._worker_thread = None
        return True

    def health(self) -> dict[str, Any]:
        with self._lock:
            thread = self._worker_thread
            return {
                "running": bool(thread and thread.is_alive()),
                "queued": len(self._queued),
                "pending": self._jobs.qsize(),
            }

    def submit(self, fn: JobFn, *args: Any, **kwargs: Any) -> bool:
        key = _job_key(fn, args, kwargs)
        with self._lock:
            if key in self._queued:
                return False
            self._queued.add(key)
            self._jobs.put((fn, args, kwargs, key))
        self.start()
        return True


job_queue = JobQueue()


def spawn(fn: JobFn, *args: Any, **kwargs: Any) -> bool:
    """Queue background work with one worker and report duplicate suppression."""
    return job_queue.submit(fn, *args, **kwargs)
