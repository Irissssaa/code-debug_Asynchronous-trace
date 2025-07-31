from typing import List, Dict, Any
from .base import RuntimePlugin
from ..tracers.async_backtrace import AsyncBacktraceTracer
from .async_backtrace_data import async_backtrace_store

class AsyncBacktracePlugin(RuntimePlugin):
    """
    A runtime plugin to capture asynchronous backtraces.
    This plugin implements Step 5 and the first part of Step 6.
    """
    def __init__(self, poll_functions_to_instrument: List[str], expansion_results: Dict[str, Any]):
        """
        Initializes the plugin with the list of poll functions to instrument
        and the future expansion results from Step 3.

        Args:
            poll_functions_to_instrument: A list of poll function names.
            expansion_results: The dictionary containing future dependency info.
        """
        self._poll_functions = poll_functions_to_instrument
        self._expansion_results = expansion_results
        
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
        This implements Step 5.
        """
        print("[rust-future-tracing] === Step 5: Setting up instrumentation for poll functions ===")
        
        # We need to pass the expansion results to the tracer so it can
        # determine the coroutine ID for each future.
        tracer_factory = lambda: AsyncBacktraceTracer(self._expansion_results)

        instrumentation = []
        for func_name in self._poll_functions:
            instrumentation.append({
                "symbol": func_name,
                "entry_tracers": [tracer_factory],
                "exit_tracers": [tracer_factory] 
            })
            print(f"  - Will instrument: {func_name}")
        
        print("[rust-future-tracing] === Step 5 complete ===")
        return instrumentation

    def process_data(self, all_traced_data: Dict[str, Any]):
        """
        This plugin does not process data directly. The data is stored in the
        `async_backtrace_store` and is intended to be displayed by the
        `inspect-async` command (Step 7).
        """
        print("[rust-future-tracing] Data collection complete. Use 'inspect-async' to view results.")
        pass
