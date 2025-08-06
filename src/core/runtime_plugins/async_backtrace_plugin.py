from typing import List, Dict, Any
from .base import RuntimePlugin
from ..tracers.async_backtrace import AsyncBacktraceTracer
from .async_backtrace_data import async_backtrace_store

class AsyncBacktracePlugin(RuntimePlugin):
    """
    A runtime plugin to capture asynchronous backtraces.
    This plugin implements Step 5 and the first part of Step 6.
    """
    def __init__(self, poll_functions_to_instrument: List[str], expansion_results: Dict[str, Any], debug_command=None):
        """
        Initializes the plugin with the list of poll functions to instrument
        and the future expansion results from Step 3.

        Args:
            poll_functions_to_instrument: A list of poll function names.
            expansion_results: The dictionary containing future dependency info.
            debug_command: The StartAsyncDebugCommand instance to use for DWARF operations.
        """
        self._poll_functions = poll_functions_to_instrument
        self._expansion_results = expansion_results
        self._debug_command = debug_command        

        # Clear any previous data and build the offset-to-name map
        async_backtrace_store.clear()
        validated_futures = self._expansion_results.get("validated_futures", {})
        async_backtrace_store.build_offset_to_name_map(validated_futures)
        
        print(f"[rust-future-tracing] Initialized AsyncBacktracePlugin for {len(self._poll_functions)} poll functions.")

    @property
    def name(self):
        """Returns the name of the plugin."""
        return "async_backtrace"

    def instrument_points(self) -> List[Dict[str, Any]]:
        """
        Defines where to set breakpoints and which tracers to run.
        This implements Step 5 by pre-computing future information for each poll function.
        """
        print("[rust-future-tracing] === Step 5: Setting up instrumentation for poll functions ===")
        
        instrumentation = []
        validated_futures = self._expansion_results.get("validated_futures", {})
        expansion_info = self._expansion_results.get("expansion_info", {})
        
        # Build a map from poll function names to their corresponding future information
        poll_to_future_map = {}
        
        # Process future structs to find their corresponding poll functions
        for future_info in validated_futures.get("future_structs", []):
            future_offset = future_info["offset"]
            future_die = future_info["die"]
            future_name = future_info["name"]
            
            # Find the coroutine ID for this future (root future in dependency tree)
            coroutine_id = self._find_coroutine_id(future_offset, expansion_info.get("ancestors", {}))
            
            # We need the debug command to convert future to poll
            # Use the passed debug_command instance to avoid creating a new one
            try:
                if self._debug_command:
                    # Build full future struct name and find corresponding poll function
                    full_future_name = self._debug_command.dieToFullName(future_die)
                    if full_future_name:
                        poll_result = self._debug_command.find_poll_function_for_future_struct(future_die, future_offset)
                        if poll_result:
                            poll_die, poll_offset = poll_result
                            poll_name = self._debug_command.dieToFullName(poll_die)
                            if poll_name:
                                poll_to_future_map[poll_name] = {
                                    "future_name": full_future_name,
                                    "coroutine_id": coroutine_id,
                                    "future_offset": future_offset
                                }
                else:
                    print(f"[rust-future-tracing] Warning: No debug command available for future {future_name}")
            except Exception as e:
                print(f"[rust-future-tracing] Warning: Could not map future {future_name} to poll function: {e}")        
	for func_name in self._poll_functions:
            future_info = poll_to_future_map.get(func_name)
            if future_info:
                # Create tracer factory with pre-computed information
                tracer_factory = lambda fi=future_info: AsyncBacktraceTracer(
                    fi["future_name"], 
                    fi["coroutine_id"], 
                    fi["future_offset"]
                )
            else:
                # Fallback: create tracer with basic information
                print(f"[rust-future-tracing] Warning: No future mapping found for {func_name}, using fallback")
                tracer_factory = lambda fn=func_name: AsyncBacktraceTracer(
                    fn,  # Use poll function name as future name
                    hash(fn) % 1000000,  # Generate a simple coroutine ID
                    0  # Unknown future offset
                )

            instrumentation.append({
                "symbol": func_name,
                "entry_tracers": [tracer_factory],
                "exit_tracers": [tracer_factory] 
            })
            print(f"  - Will instrument: {func_name}")
        
        print("[rust-future-tracing] === Step 5 complete ===")
        return instrumentation

    def _find_coroutine_id(self, future_offset: int, ancestors_map: Dict[int, List[int]]) -> int:
        """
        Finds the root future (coroutine) for a given future offset by
        traversing the ancestors map. The root's offset is the coroutine ID.
        """
        current_offset = future_offset
        # Keep going up the ancestor chain until we find the root
        while current_offset in ancestors_map and ancestors_map[current_offset]:
            # Take the first ancestor (there might be multiple in complex cases)
            current_offset = ancestors_map[current_offset][0]
        return current_offset

    def process_data(self, all_traced_data: Dict[str, Any]):
        """
        This plugin does not process data directly. The data is stored in the
        `async_backtrace_store` and is intended to be displayed by the
        `inspect-async` command (Step 7).
        """
        print("[rust-future-tracing] Data collection complete. Use 'inspect-async' to view results.")
        pass
