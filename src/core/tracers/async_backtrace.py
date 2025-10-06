"""
This tracer implements Step 6 of the async debugging process.
It captures asynchronous backtrace information by tracking the entry and exit
of poll functions using pre-computed future information.
"""
import gdb
import time
from typing import List
from .base import Tracer
from ..config import ASYNC_STACK_HEAD_LIMIT, ASYNC_STACK_TAIL_LIMIT
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
            tid = getattr(inferior_thread, "ptid", (0, 0, 0))[1]
            
            # Snapshot the previously recorded stack for event inference
            stack_container = self.backtraces[pid][tid][self.coroutine_id]
            previous_stack = list(stack_container)

            # Capture the current call stack from GDB and replace stored stack
            current_stack = self._capture_call_stack()
            stack_container.clear()
            stack_container.extend(current_stack)

            # Determine event type heuristically based on stack depth changes
            event = "snapshot"
            if len(current_stack) > len(previous_stack):
                event = "entry"
            elif len(current_stack) < len(previous_stack):
                event = "exit"

            recency_meta = async_backtrace_store.record_thread_update(pid, tid, self.coroutine_id)

            self.data = {
                "event": event,
                "coroutine": self.coroutine_id,
                "future": self.future_name,
                "future_offset": self.future_offset,
                "stack_depth": len(current_stack),
                "stack_snapshot": current_stack,
                "process_id": pid,
                "thread_id": tid,
                "thread_update_sequence": recency_meta.get("sequence"),
                "thread_update_timestamp": recency_meta.get("timestamp"),
            }

            self.show_coroutine_lists()
            # Print current backtrace for comparison with async stack
            # print(f"[rust-future-tracing] Current backtrace for coroutine {self.coroutine_id}: \n{gdb.execute('bt', to_string=True)}\n\n\n\n\n")

        except Exception as e:
            self.data = f"Error: {e}"
            # This can be noisy, so only print if necessary for debugging
            # print(f"[rust-future-tracing] tracer warning: {e}")

    def _capture_call_stack(self, max_depth: int = 512) -> List[str]:
        """Capture the current call stack from GDB and return it from root to leaf."""
        frames: List[str] = []
        frame = gdb.newest_frame()
        depth = 0

        while frame is not None and depth < max_depth:
            name = frame.name()
            if not name:
                try:
                    block = frame.block()
                    if block and block.function:
                        name = block.function.print_name
                except gdb.error:
                    name = None
            if not name:
                try:
                    sal = frame.find_sal()
                    if sal and sal.symtab and sal.symtab.filename:
                        name = f"{sal.symtab.filename}:{sal.line}"
                except gdb.error:
                    name = None
            if not name:
                try:
                    pc = frame.pc()
                    name = f"<unknown@0x{pc:x}>"
                except gdb.error:
                    name = "<unknown>"

            frames.append(name)
            frame = frame.older()
            depth += 1

        frames.reverse()  # Oldest frame first for display consistency
        return frames

    def show_coroutine_lists(self):
        offset_to_name = async_backtrace_store.get_offset_to_name_map()
        thread_recency = async_backtrace_store.get_thread_recency()
        now = time.time()

        if not self.backtraces:
            print("[rust-future-tracing] No asynchronous backtrace data collected.")
            print("Hint: Run the 'start-async-debug' command and then 'continue' or 'run' the program.")
            return

        print("=" * 80)
        print(" " * 28 + "Asynchronous Backtraces")
        print("=" * 80)

        for pid, thread_map in self.backtraces.items():
            pid_recency = thread_recency.get(pid, {})
            latest_tid = None
            latest_sequence = -1
            for tid, meta in pid_recency.items():
                seq = meta.get("sequence", -1)
                if seq > latest_sequence:
                    latest_sequence = seq
                    latest_tid = tid

            print(f"Process {pid}:")
            for tid, coroutine_map in thread_map.items():
                meta = pid_recency.get(tid)
                marker = ""
                if meta and tid == latest_tid:
                    marker = " (most recent thread)"

                print(f"  Thread {tid}{marker}:")
                if meta:
                    updated_delta = max(0.0, now - meta.get("timestamp", now))
                    coroutine_hint = meta.get("coroutine_id")
                    hint_parts = []
                    if coroutine_hint is not None:
                        hint_parts.append(f"coroutine {coroutine_hint}")
                    hint_parts.append(f"updated {updated_delta:.2f}s ago")
                    print(f"    Last update: {', '.join(hint_parts)}")

                if not coroutine_map:
                    print("    No coroutines found.")
                    continue
                
                for coroutine_id, stack in coroutine_map.items():
                    coroutine_name = offset_to_name.get(coroutine_id, f"Coroutine<{coroutine_id}>")
                    print(f"    Coroutine '{coroutine_name}' (ID: {coroutine_id}):")
                    
                    if not stack:
                        print("      Stack is empty.")
                    else:
                        for frame in self._iter_display_frames(stack):
                            print(f"      {frame}")
        
        print("=" * 80)

    def _iter_display_frames(self, stack: List[str]):
        """Return stack frames respecting head/tail limits with ellipsis markers."""
        total = len(stack)
        head_limit = max(0, ASYNC_STACK_HEAD_LIMIT)
        tail_limit = max(0, ASYNC_STACK_TAIL_LIMIT)

        if total == 0 or (head_limit + tail_limit) == 0:
            return []

        if head_limit + tail_limit >= total:
            return stack

        head_count = min(head_limit, total)
        tail_count = min(tail_limit, max(total - head_count, 0))

        if head_count + tail_count >= total:
            return stack

        display = list(stack[:head_count])

        if tail_count > 0:
            if head_count < total - tail_count:
                display.append("...")
            display.extend(stack[-tail_count:])
        else:
            display.append("...")

        return display

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass

    def __str__(self) -> str:
        return "AsyncBacktraceTracer"
