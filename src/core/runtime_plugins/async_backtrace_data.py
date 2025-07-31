"""
This module defines the data store for asynchronous backtrace information.
It uses a singleton pattern to ensure that all parts of the debugger
(plugins, tracers, commands) access the same data instance.
"""
from collections import defaultdict

class _AsyncBacktraceDataStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_AsyncBacktraceDataStore, cls).__new__(cls)
            # The multi-level dictionary to store async backtraces:
            # dict[process_id][thread_id][coroutine_id] -> [future_name, ...]
            cls._instance.backtraces = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            # Helper to map future offsets to names for quick lookups
            cls._instance.offset_to_name_map = {}
        return cls._instance

    def get_backtraces(self):
        """Returns the main backtrace data structure."""
        return self.backtraces

    def get_offset_to_name_map(self):
        """Returns the offset-to-name map."""
        return self.offset_to_name_map
        
    def build_offset_to_name_map(self, validated_futures: dict):
        """
        Builds a map from DIE offset to future name for quick lookups.
        This should be called once before tracing starts.
        """
        self.offset_to_name_map.clear()
        
        for future_info in validated_futures.get("future_structs", []):
            self.offset_to_name_map[future_info["offset"]] = future_info["name"]
        
        for func_info in validated_futures.get("async_functions", []):
            self.offset_to_name_map[func_info["offset"]] = func_info["name"]

    def clear(self):
        """Clears all stored data."""
        self.backtraces.clear()
        self.offset_to_name_map.clear()

# Singleton instance to be imported by other modules
async_backtrace_store = _AsyncBacktraceDataStore()

