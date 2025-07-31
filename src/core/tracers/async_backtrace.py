"""
This tracer implements Step 6 of the async debugging process.
It captures asynchronous backtrace information by tracking the entry and exit
of poll functions.
"""
import gdb
from .base import Tracer
from ..runtime_plugins.async_backtrace_data import async_backtrace_store
from typing import Dict, Any, Optional

class AsyncBacktraceTracer(Tracer):
    """
    A tracer that builds an asynchronous call stack.
    """
    def __init__(self, expansion_results: Dict[str, Any]):
        super().__init__()
        self.expansion_results = expansion_results
        self.ancestry_map = expansion_results.get("expansion_info", {}).get("ancestry_map", {})
        self.offset_to_name = async_backtrace_store.get_offset_to_name_map()
        self.backtraces = async_backtrace_store.get_backtraces()

    def _find_coroutine_id(self, future_offset: int) -> int:
        """
        Finds the root future (coroutine) for a given future offset by
        traversing the ancestry map. The root's offset is the coroutine ID.
        """
        current_offset = future_offset
        while current_offset in self.ancestry_map:
            parent_offset = self.ancestry_map[current_offset]
            # In the ancestry map, a node's parent is itself if it's a root.
            if parent_offset == current_offset:
                break
            current_offset = parent_offset
        return current_offset

    def start(self, inferior_thread: gdb.Thread):
        """
        Called on both entry and exit of a poll function to update the async stack.
        """
        try:
            pid = gdb.selected_inferior().pid
            tid = inferior_thread.ptid[1]
            frame = gdb.selected_frame()
            
            if not frame or not frame.name():
                return

            # The first argument to a poll function is `Pin<&mut Self>`, where `Self`
            # is the future struct. We can get its address.
            arg_self = frame.read_var('self')
            future_address = int(arg_self.address)

            # We need the DIE offset of the future to find its dependencies.
            # We can get this from the type of the `self` argument.
            future_type = arg_self.type.strip_typedefs()
            
            # The type might be a pointer, so we get the target type.
            if future_type.code == gdb.TYPE_CODE_PTR:
                future_type = future_type.target()

            # This is a trick to get the DIE offset from the type object
            future_offset = future_type.tag.split("::")[-1]
            if not future_offset:
                print(f"[rust-future-tracing] tracer warning: Could not get future offset for type {future_type}")
                return
            
            future_offset = int(future_offset)
            future_name = self.offset_to_name.get(future_offset, f"UnknownFuture<{future_offset}>")
            
            coroutine_id = self._find_coroutine_id(future_offset)
            
            # Get the specific async stack for this coroutine
            async_stack = self.backtraces[pid][tid][coroutine_id]

            # Determine if this is an entry or exit event
            is_exit = async_stack and async_stack[-1] == future_name

            if is_exit:
                # On exit, pop from the stack
                async_stack.pop()
                self.data = {"event": "exit", "coroutine": coroutine_id, "future": future_name, "stack_depth": len(async_stack)}
            else:
                # On entry, push to the stack
                async_stack.append(future_name)
                self.data = {"event": "entry", "coroutine": coroutine_id, "future": future_name, "stack_depth": len(async_stack)}

        except gdb.error as e:
            self.data = f"Error: {e}"
            # This can be noisy, so only print if necessary for debugging
            # print(f"[rust-future-tracing] tracer warning: {e}")

    def stop(self):
        """This is a single-shot tracer, so stop is a no-op."""
        pass

    def __str__(self) -> str:
        return "AsyncBacktraceTracer"
