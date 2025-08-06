"""
This tracer implements Step 6 of the async debugging process.
It captures asynchronous backtrace information by tracking the entry and exit
of poll functions using pre-computed future information.
"""
import gdb
from .base import Tracer
from ..runtime_plugins.async_backtrace_data import async_backtrace_store

class AsyncBacktraceTracer(Tracer):
    """
    A tracer that builds an asynchronous call stack.
    """
    def __init__(self, future_name: str, coroutine_id: int, future_offset: int):
        super().__init__()
        # Pre-computed information stored when setting up instrumentation
        self.future_name = future_name
        self.coroutine_id = coroutine_id
        self.future_offset = future_offset
        self.backtraces = async_backtrace_store.get_backtraces()

    def start(self, inferior_thread: gdb.Thread):
        """
        Called on both entry and exit of a poll function to update the async stack.
	Uses pre-computed future information instead of trying to extract it at runtime.
        """
        try:
            pid = gdb.selected_inferior().pid
            tid = inferior_thread.ptid[1]
            
            # Get the specific async stack for this coroutine
            async_stack = self.backtraces[pid][tid][self.coroutine_id]

            # Determine if this is an entry or exit event
            is_exit = async_stack and async_stack[-1] == self.future_name

            if is_exit:
                # On exit, pop from the stack
                async_stack.pop()
                self.data = {
                    "event": "exit", 
                    "coroutine": self.coroutine_id, 
                    "future": self.future_name, 
                    "future_offset": self.future_offset,
                    "stack_depth": len(async_stack)
                }
            else:
                # On entry, push to the stack
                async_stack.append(self.future_name)
                self.data = {
                    "event": "entry", 
                    "coroutine": self.coroutine_id, 
                    "future": self.future_name,
                    "future_offset": self.future_offset, 
                    "stack_depth": len(async_stack)
                }

        except Exception as e:
            self.data = f"Error: {e}"
            # This can be noisy, so only print if necessary for debugging
            # print(f"[rust-future-tracing] tracer warning: {e}")

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass

    def __str__(self) -> str:
        return "AsyncBacktraceTracer"
