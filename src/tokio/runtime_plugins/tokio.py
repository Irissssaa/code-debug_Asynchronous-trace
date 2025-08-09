import gdb
from gdb_debugger.runtime_plugins.base import RuntimePlugin
from gdb_debugger.runtime_plugins.tokio_model import Runtime
from gdb_debugger.tracers.variable import VariableTracer
from gdb_debugger.tracers.backtrace import BacktraceTracer
from gdb_debugger.tracers.tokio_task_id import TokioTaskIDTracer
from gdb_debugger.tracers.task_list import TaskListTracer

# --- Tracer Factory Functions ---

def new_task_id_tracer():
    """Tracer for the raw u64 inside the tokio::task::Id newtype."""
    return VariableTracer("id.__0", scope='local')

def self_tracer():
    """Tracer for the raw pointer inside the RawTask struct."""
    return VariableTracer("self.ptr.pointer", scope='local')

def poll_task_id_tracer():
    """
    Tracer for the task ID from the vtable of a polled task.
    """
    return TokioTaskIDTracer()

def task_list_tracer():
    """
    Tracer for the owned task list, found via the `self` pointer.
    """
    return TaskListTracer()

def new_task_backtrace_tracer():
    """Backtrace tracer for RawTask::new to find the spawn location."""
    return BacktraceTracer()

def thread_id_tracer():
    """A tracer to get the current thread's ID."""
    return gdb.selected_thread().ptid


# --- Plugin Implementation ---

class TokioPlugin(RuntimePlugin):
    """A plugin to instrument the Tokio runtime."""

    @property
    def name(self):
        return "tokio"

    def instrument_points(self):
        """
        Defines breakpoints for key Tokio functions to trace task lifecycle events.
        """
        return [
            {
                "symbol": "tokio::runtime::task::raw::RawTask::new",
                "entry_tracers": [new_task_id_tracer, new_task_backtrace_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::poll",
                "entry_tracers": [self_tracer, poll_task_id_tracer, task_list_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::shutdown",
                "entry_tracers": [self_tracer],
                "exit_tracers": [],
            },
            {
                "symbol": "tokio::runtime::task::raw::RawTask::dealloc",
                "entry_tracers": [self_tracer],
                "exit_tracers": [],
            },
        ]

    def process_data(self, all_traced_data: dict):
        """
        Builds a model of the runtime from the traced data and prints a report.
        """
        print("\n[gdb_debugger] ----- Tokio Runtime Report -----")
        runtime = self._build_runtime_model(all_traced_data)
        self._print_task_summary(runtime)
        print("\n[gdb_debugger] -------------------------------------\n")

    def _build_runtime_model(self, all_traced_data: dict) -> Runtime:
        runtime = Runtime()
        pointer_to_id = {}

        # Process task creations first to populate the tasks
        if "tokio::runtime::task::raw::RawTask::new" in all_traced_data:
            for invocation in all_traced_data["tokio::runtime::task::raw::RawTask::new"]:
                entry_data = invocation.get('entry_tracers', {})
                task_id = entry_data.get('VariableTracer(id.__0)')
                backtrace = entry_data.get('BacktraceTracer')
                
                if isinstance(task_id, int):
                    runtime.get_or_create_task(task_id, backtrace)

        # Process polls to link pointers to IDs and count polls
        if "tokio::runtime::task::raw::RawTask::poll" in all_traced_data:
            for invocation in all_traced_data["tokio::runtime::task::raw::RawTask::poll"]:
                entry_data = invocation.get('entry_tracers', {})
                thread_id = invocation.get('thread_id')
                task_id = entry_data.get('TokioTaskIDTracer')
                task_ptr = entry_data.get('VariableTracer(self.ptr.pointer)')
                task_list_val = entry_data.get('TaskListTracer')

                if isinstance(task_id, int):
                    task = runtime.get_or_create_task(task_id)
                    task.inc_poll()
                    if isinstance(task_ptr, int):
                        pointer_to_id[task_ptr] = task_id
                        task.add_pointer(task_ptr)
                
                if thread_id and "Error" not in str(task_list_val) and isinstance(task_list_val, gdb.Value):
                    runtime.thread_task_lists[thread_id] = task_list_val

        # Process drops using the pointer-to-ID mapping
        def process_drops(symbol_name):
            if symbol_name in all_traced_data:
                for invocation in all_traced_data[symbol_name]:
                    entry_data = invocation.get('entry_tracers', {})
                    task_ptr = entry_data.get('VariableTracer(self.ptr.pointer)')
                    
                    if isinstance(task_ptr, int) and task_ptr in pointer_to_id:
                        task_id = pointer_to_id[task_ptr]
                        task = runtime.get_or_create_task(task_id)
                        task.set_dropped()
        
        process_drops("tokio::runtime::task::raw::RawTask::shutdown")
        process_drops("tokio::runtime::task::raw::RawTask::dealloc")

        return runtime

    def _print_task_summary(self, runtime: Runtime):
        if not runtime.tasks:
            print("No tasks were traced.")
            return

        # Header
        header = f"{'ID':<5} {'Polls':<7} {'Lifetime (s)':<15} {'Spawn Location':<60}"
        print(header)
        print("-" * 100)

        # Rows
        for task_id in sorted(runtime.tasks.keys()):
            task = runtime.tasks[task_id]
            lifetime_secs = f"{task.lifetime.total_seconds():.4f}"
            
            # Truncate spawn location for display
            spawn_loc = task.spawn_location
            if len(spawn_loc) > 58:
                spawn_loc = "..." + spawn_loc[-55:]
            
            row = f"{task.id:<5} {task.poll_count:<7} {lifetime_secs:<15} {spawn_loc:<60}"
            print(row)

    def invoke(self, arg, from_tty):
        if not gdb.selected_inferior().is_valid():
            print("No inferior process is currently being debugged.")
            return

        # This is more reliable than a live inspection.
        runtime = plugin._build_runtime_model(traced_data)
        worker_threads = self._find_worker_threads()

        if not worker_threads:
            print("No worker threads found.")
            return

        print(f"Found {len(worker_threads)} worker threads:")
        for thread in worker_threads:
            print(f"  - Thread {thread.ptid}: {thread.name}")
            
            # In the new design, we don't need to find CONTEXT. We can
            # get the task list directly from the last poll event.
            last_poll_task_list = None
            if "tokio::runtime::task::raw::RawTask::poll" in traced_data:
                for invocation in reversed(traced_data["tokio::runtime::task::raw::RawTask::poll"]):
                    if invocation.get("thread_id") == thread.ptid:
                        task_list_val = invocation.get('entry_tracers', {}).get('TaskListTracer')
                        if "Error" not in str(task_list_val) and isinstance(task_list_val, gdb.Value):
                            last_poll_task_list = task_list_val
                            break
            
            if not last_poll_task_list:
                print(f"    Task List: Not captured. (Has this thread polled a task?)")
            else:
                print(f"    Task List: Captured")
                task_headers = self._extract_task_headers(last_poll_task_list)
                for header_addr in task_headers:
                    print(f"    - Task Header: {hex(header_addr)}")

    def _extract_task_headers(self, owned_tasks_val: gdb.Value):
        """
        Walks the intrusive linked list in an OwnedTasks struct
        to extract all task header pointers.
        """
        try:
            task_list = owned_tasks_val['list']
            
            # Now, walk the linked list.
            head = task_list['head']
            # ... rest of the method ...
        except Exception as e:
            print(f"Error extracting task headers: {e}")
            return []

# A single instance of the plugin to be loaded by the main script.
plugin = TokioPlugin() 