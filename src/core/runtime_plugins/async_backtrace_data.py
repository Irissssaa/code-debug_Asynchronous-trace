"""
This module defines the data store for asynchronous backtrace information.
It uses a singleton pattern to ensure that all parts of the debugger
(plugins, tracers, commands) access the same data instance.
"""
from collections import defaultdict
import itertools
import time
from typing import Optional, Dict, Any

class _AsyncBacktraceDataStore:
    _instance = None
    backtraces: Dict[int, Dict[int, Dict[int, list]]]
    offset_to_name_map: Dict[int, str]
    thread_recency: Dict[int, Dict[int, Dict[str, Any]]]
    _update_counter: itertools.count

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_AsyncBacktraceDataStore, cls).__new__(cls)
            # The multi-level dictionary to store async backtraces:
            # dict[process_id][thread_id][coroutine_id] -> [future_name, ...]
            cls._instance.backtraces = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            # Helper to map future offsets to names for quick lookups
            cls._instance.offset_to_name_map = {}
            # Track recency information per thread per process
            cls._instance.thread_recency = defaultdict(lambda: defaultdict(dict))
            cls._instance._update_counter = itertools.count()
        return cls._instance

    def get_backtraces(self):
        """Returns the main backtrace data structure."""
        return self.backtraces

    def get_offset_to_name_map(self):
        """Returns the offset-to-name map."""
        return self.offset_to_name_map

    def get_thread_recency(self):
        """Returns metadata describing the last update for each thread."""
        return self.thread_recency

    def record_thread_update(self, pid: int, tid: int, coroutine_id: int, timestamp: Optional[float] = None):
        """Record that a given thread just updated its async stack."""
        if timestamp is None:
            timestamp = time.time()

        sequence = next(self._update_counter)
        metadata = self.thread_recency[pid][tid]
        metadata["sequence"] = sequence
        metadata["timestamp"] = timestamp
        metadata["coroutine_id"] = coroutine_id
        return metadata
        
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
        self.thread_recency.clear()
        self._update_counter = itertools.count()

# Singleton instance to be imported by other modules
async_backtrace_store = _AsyncBacktraceDataStore()
