# different compilers may produce different poll types
poll_type = "core::task::poll::Poll"
PLUGIN_NAME = "tokio"
# with / 
result_path = "results/"

# Path (or glob) to the LLVM call graph DOT file used to discover synchronous descendants.
# When empty, the debugger will attempt to auto-discover the most recent *.callgraph.dot file.
CALL_GRAPH_DOT_PATH = ""

# Toggle synchronous descendant instrumentation discovered via the LLVM call graph.
ENABLE_SYNC_DESCENDANTS = True

# Maximum depth when traversing synchronous descendants in the call graph.
SYNC_DESCENDANT_DEPTH = 2

# Top-level namespace prefixes to ignore when collecting synchronous descendants.
SYNC_DESCENDANT_EXCLUDE_PREFIXES = {"core", "alloc", "std", "llvm", "serde", "icu"}

# Toggle asynchronous descendant instrumentation discovered via dependency expansion.
ENABLE_ASYNC_DESCENDANTS = True

# Maximum number of frames to display from the start and end of each coroutine stack.
# Set to 0 to suppress the corresponding section.
ASYNC_STACK_HEAD_LIMIT = 5
ASYNC_STACK_TAIL_LIMIT = 5