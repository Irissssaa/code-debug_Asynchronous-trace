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

            self.show_coroutine_lists()
            # Print current backtrace for comparison with async stack
            # print(f"[rust-future-tracing] Current backtrace for coroutine {self.coroutine_id}: \n{gdb.execute('bt', to_string=True)}\n\n\n\n\n")

        except Exception as e:
            self.data = f"Error: {e}"
            # This can be noisy, so only print if necessary for debugging
            # print(f"[rust-future-tracing] tracer warning: {e}")

    def show_coroutine_lists(self):
        offset_to_name = async_backtrace_store.get_offset_to_name_map()

        if not self.backtraces:
            print("[rust-future-tracing] No asynchronous backtrace data collected.")
            print("Hint: Run the 'start-async-debug' command and then 'continue' or 'run' the program.")
            return

        print("=" * 80)
        print(" " * 28 + "Asynchronous Backtraces")
        print("=" * 80)

        for pid, thread_map in self.backtraces.items():
            print(f"Process {pid}:")
            for tid, coroutine_map in thread_map.items():
                print(f"  Thread {tid}:")
                if not coroutine_map:
                    print("    No coroutines found.")
                    continue
                
                for coroutine_id, stack in coroutine_map.items():
                    coroutine_name = offset_to_name.get(coroutine_id, f"Coroutine<{coroutine_id}>")
                    print(f"    Coroutine '{coroutine_name}' (ID: {coroutine_id}):")
                    
                    if not stack:
                        print("      Stack is empty.")
                    else:
                        # Print stack from top to bottom
                        for i, future_name in enumerate(stack):
                            indent = "      " + "  " * i
                            arrow = "->" if i > 0 else "  "
                            print(f"{indent}{arrow} {future_name}")
        
        print("=" * 80)

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass

    def __str__(self) -> str:
        return "AsyncBacktraceTracer"
