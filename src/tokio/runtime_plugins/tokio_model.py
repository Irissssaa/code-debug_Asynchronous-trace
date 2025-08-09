import datetime

class Task:
    """Represents a single Tokio task and its collected metrics."""
    def __init__(self, task_id, backtrace=None):
        self.id = task_id
        self.pointers = set()
        self.poll_count = 0
        self.created_at = datetime.datetime.now()
        self.dropped_at = None
        self.spawn_location = self._extract_spawn_location(backtrace)

    def add_pointer(self, ptr):
        if ptr:
            self.pointers.add(ptr)

    def inc_poll(self):
        self.poll_count += 1

    def set_dropped(self):
        self.dropped_at = datetime.datetime.now()

    @property
    def is_dropped(self):
        return self.dropped_at is not None

    @property
    def lifetime(self):
        """Returns the task's lifetime as a timedelta."""
        end_time = self.dropped_at or datetime.datetime.now()
        return end_time - self.created_at

    def _extract_spawn_location(self, backtrace):
        """
        A simple heuristic to find where a task was spawned. It looks for the
        first frame in the backtrace that isn't inside tokio's own code.
        """
        if not backtrace:
            return "Unknown"

        for frame in backtrace:
            name = frame.get("name")
            if name and not name.startswith("tokio::"):
                return name
        return "Unknown (in tokio)"


class Runtime:
    """Represents the state of the Tokio runtime and all its tasks."""
    def __init__(self):
        self.tasks = {} # Dict of task_id -> Task
        self.thread_task_lists = {} # Dict of thread_id -> last known OwnedTasks gdb.Value

    def get_or_create_task(self, task_id, backtrace=None) -> Task:
        """Gets a task by ID, creating it if it doesn't exist."""
        if task_id not in self.tasks:
            self.tasks[task_id] = Task(task_id, backtrace)
        return self.tasks[task_id] 