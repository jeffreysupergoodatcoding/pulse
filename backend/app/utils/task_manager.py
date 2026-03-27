"""
In-memory async task registry.
Mirrors MiroFish's task_manager pattern.
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import Any, Callable


class Task:
    def __init__(self, task_id: str, name: str):
        self.task_id = task_id
        self.name = name
        self.status = "pending"       # pending | running | completed | error
        self.progress = 0             # 0-100
        self.result: Any = None
        self.error: str | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskManager:
    """Thread-safe in-memory task registry."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(self, name: str) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(task_id=task_id, name=name)
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def update(
        self,
        task_id: str,
        status: str | None = None,
        progress: int | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if status is not None:
                task.status = status
            if progress is not None:
                task.progress = progress
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            task.updated_at = datetime.now(timezone.utc).isoformat()
            return task

    def run_async(self, name: str, fn: Callable, *args, **kwargs) -> Task:
        """Create a task and run fn in a background thread."""
        task = self.create(name)
        self.update(task.task_id, status="running")

        def _run():
            try:
                result = fn(task, *args, **kwargs)
                self.update(task.task_id, status="completed", progress=100, result=result)
            except Exception as exc:
                self.update(task.task_id, status="error", error=str(exc))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return task

    def list_all(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]


# Module-level singleton used by all routes
task_manager = TaskManager()
