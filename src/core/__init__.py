import gdb
import os
import sys
import importlib
import re

# --- Setup ---

# import plugin name from config.py
# currently we only allow 1 plugin at a time
from core.config import PLUGIN_NAME
if not PLUGIN_NAME:
    print("[rust-future-tracing] No plugin name specified in config.py. Please set PLUGIN_NAME.")
    sys.exit(1)

from core.init_dwarf_analysis import get_dwarf_tree
from core.dwarf.tree import load_children
from core.dwarf.dwarfutil import safe_DIE_name, DIE_has_name

# --- Global Data Store ---

# A dictionary to hold all data collected by tracers.
# Structure: {
#   "symbol_name": [
#     {
#       "thread_id": gdb.Thread.ptid,
#       "entry_tracers": { "TracerClassName": data, ... },
#       "exit_tracers": { "TracerClassName": data, ... }
#     },
#     ...
#   ],
#   ...
# }
traced_data = {}

# This list holds temporary commands for breakpoints.
bp_commands = []

def run_tracers(symbol_name, entry_tracers, exit_tracers):
    """
    Called by the temporary breakpoint's command to run tracers
    after the function prolog has safely completed.
    """
    thread = gdb.selected_thread()
    if symbol_name not in traced_data:
        traced_data[symbol_name] = []
    
    invocation_data = {
        "thread_id": thread.ptid,
        "entry_tracers": {},
        "exit_tracers": {},
    }
    traced_data[symbol_name].append(invocation_data)

    for tracer_factory in entry_tracers:
        tracer = tracer_factory()
        tracer.start(thread)
        invocation_data["entry_tracers"][str(tracer)] = tracer.read_data()

    if exit_tracers:
        FinishBreakpoint(gdb.newest_frame(), symbol_name, invocation_data, exit_tracers)


# --- Load Plugin (Plugin loaders load tracers)---

# todo: 自动搜索/加载多个插件，这个工作比较次要，所以暂时先不做：
# 1. 查找并加载指定目录下的所有插件
# 2. 插件之间如何配合
try:
    plugin = importlib.import_module(PLUGIN_NAME)
    print(f"[rust-future-tracing] Loaded runtime plugin: {PLUGIN_NAME} (currently does nothing)")
except (ImportError, AttributeError) as e:
    print(f"[rust-future-tracing] ERROR: Failed to load plugin '{PLUGIN_NAME}': {e}.")
    plugin = None


# --- Breakpoint Implementation ---

class FinishBreakpoint(gdb.FinishBreakpoint):
    """
    A finish breakpoint that runs tracers when a function call completes.
    """
    def __init__(self, frame: gdb.Frame, symbol_name: str, invocation_data: dict, exit_tracers: list):
        super().__init__(frame, internal=True)
        self.symbol_name = symbol_name
        self.invocation_data = invocation_data
        self.exit_tracers = exit_tracers

    def stop(self):
        """Called when the frame is about to return."""
        thread = gdb.selected_thread()
        for tracer_factory in self.exit_tracers:
            tracer = tracer_factory()
            tracer.start(thread)
            self.invocation_data["exit_tracers"][str(tracer)] = tracer.read_data()
        return False  # Always continue execution

    def out_of_scope(self):
        """Called when the frame is unwound, e.g., by an exception."""
        self.invocation_data["exit_tracers"]["error"] = "out_of_scope (e.g. exception)"


class EntryBreakpoint(gdb.Breakpoint):
    """
    A two-stage breakpoint to reliably trace function arguments by
    stepping over the function's prolog code.
    """
    def __init__(self, symbol: str, entry_tracers: list, exit_tracers: list):
        super().__init__(symbol, internal=True)
        self.symbol_name = symbol
        self.entry_tracers = entry_tracers
        self.exit_tracers = exit_tracers

    def stop(self):
        # This breakpoint hits at the raw function entry. We now set a
        # temporary breakpoint at the same spot to run our tracers.
        pc = gdb.selected_frame().pc()
        t_break = gdb.Breakpoint(f"*{pc}", gdb.BP_BREAKPOINT, internal=True, temporary=True)
        
        # We store the Python function to call in a global list and use its
        # index to call it from the breakpoint's command string.
        cmd_index = len(bp_commands)
        bp_commands.append(lambda: run_tracers(self.symbol_name, self.entry_tracers, self.exit_tracers))
        
        # The command string for the temporary breakpoint. It calls our Python
        # function, then tells GDB to continue automatically.
        t_break.commands = f"""
python bp_commands[{cmd_index}]()
continue
"""
        return False # Immediately continue to hit the temporary breakpoint.


# --- GDB Commands ---

class StartAsyncDebugCommand(gdb.Command):
    """GDB command to start the async debugger and set breakpoints."""
    def __init__(self):
        super().__init__("start-async-debug", gdb.COMMAND_USER)

    def parse_poll_function_hierarchy(self, poll_fn_name):
        """
        Parse a poll function name into hierarchical components for DWARF analysis.
        
        This method implements the parsing logic described in dwarf_analyzer.md line 509:
        "将 poll 函数名拆分成层级，比如说 reqwest::get::{async_fn#0} 拆分成 reqwest get 和 {async_fn#0}"
        
        Args:
            poll_fn_name (str): Poll function name from GDB, which may include full signatures
            
        Returns:
            list: Hierarchical namespace components suitable for DWARF DIE tree navigation
            
        Examples:
            "static fn reqwest::get::{async_fn#0}<&str>(...)" 
                -> ["reqwest", "get", "{async_fn#0}<&str>"]
            "hyper::client::conn::http1::{impl#1}::ready::{async_fn#0}" 
                -> ["hyper", "client", "conn", "http1", "{impl#1}", "ready", "{async_fn#0}"]
            "h2::client::bind_connection::{async_fn#0}" 
                -> ["h2", "client", "bind_connection", "{async_fn#0}"]
                
        Note:
            - Removes "static fn " prefix and function parameters (parentheses)
            - Preserves generic type parameters in angle brackets for DWARF navigation
            - Preserves {async_fn#0}, {impl#N}, {closure_env#N} markers for DWARF navigation
            - Works with both async function polls and regular function polls
        """
        import re
        
        # Remove function signature parts (parameters and return type)
        # First remove the "static fn " prefix if present
        cleaned_name = re.sub(r'^static fn\s+', '', poll_fn_name)
        
        # Find the function name part before the first opening parenthesis (but keep angle brackets)
        # This handles cases like "reqwest::get::{async_fn#0}<&str>(...)"
        match = re.match(r'([^(]+)', cleaned_name)
        if not match:
            return []
        
        function_path = match.group(1).strip()
        
        # Split by "::" but be careful not to split inside angle brackets
        components = []
        current_component = ""
        bracket_depth = 0
        
        i = 0
        while i < len(function_path):
            if function_path[i] == '<':
                bracket_depth += 1
                current_component += function_path[i]
            elif function_path[i] == '>':
                bracket_depth -= 1
                current_component += function_path[i]
            elif function_path[i:i+2] == '::' and bracket_depth == 0:
                # Only split on :: when we're not inside angle brackets
                if current_component.strip():
                    components.append(current_component.strip())
                current_component = ""
                i += 1  # Skip the second ':'
            else:
                current_component += function_path[i]
            i += 1
        
        # Add the last component
        if current_component.strip():
            components.append(current_component.strip())
        
        return components

    def debug_print_compilation_unit(self, cu_index=0, max_depth=2):
        """
        Debug method to print the structure of a compilation unit.
        This helps us understand the DWARF tree structure for development.
        
        Args:
            cu_index (int): Index of compilation unit to print (default: 0)
            max_depth (int): Maximum depth to print (default: 2)
        """
        from .init_dwarf_analysis import get_dwarf_tree
        from .dwarf.tree import load_children
        from .dwarf.dwarfutil import safe_DIE_name
        
        tree = get_dwarf_tree()
        if not tree:
            print("Error: DWARF tree not initialized. Run 'init-dwarf-analysis' first.")
            return
        
        if cu_index >= len(tree.top_dies):
            print(f"Error: CU index {cu_index} out of range. Available: 0-{len(tree.top_dies)-1}")
            return
        
        def print_die_tree(die, depth=0, max_depth=2):
            if depth > max_depth:
                return
            
            indent = "  " * depth
            die_name = safe_DIE_name(die, "<no name>")
            tag = die.tag if hasattr(die, 'tag') else "<no tag>"
            
            print(f"{indent}{tag}: {die_name}")
            
            if die.has_children and depth < max_depth:
                load_children(die, True)  # Load and sort children
                for child in die._children[:10]:  # Limit to first 10 children
                    print_die_tree(child, depth + 1, max_depth)
                if len(die._children) > 10:
                    print(f"{indent}  ... ({len(die._children) - 10} more children)")
        
        cu_die = tree.top_dies[cu_index]
        print(f"=== Compilation Unit {cu_index} Structure ===")
        print_die_tree(cu_die, 0, max_depth)

    def _get_tree_safely(self):
        """Validate that DWARF environment is ready, returning the DWARF tree.s"""
        tree = get_dwarf_tree()
        if not tree:
            raise Exception("DWARF tree not initialized. Run 'init-dwarf-analysis' first.")
        
        if not tree.top_dies:
            raise Exception("No compilation units found in DWARF tree")
        
        return tree

    def _safe_die_operation(self, operation, die, *args, **kwargs):
        """Safely perform DIE operations with error handling"""
        try:
            return operation(die, *args, **kwargs)
        except Exception as e:
            die_name = safe_DIE_name(die, "<unknown>")
            print(f"Warning: Error processing DIE '{die_name}': {e}")
            return None
    
    def debug_print_hierarchy_search(self, poll_fn_name):
        """Debug version that prints search progress"""
        hierarchy = self.parse_poll_function_hierarchy(poll_fn_name)
        print(f"Searching for hierarchy: {hierarchy}")
        
        tree = get_dwarf_tree()
        for i, cu_die in enumerate(tree.top_dies[:5]):  # Limit for testing
            cu_name = safe_DIE_name(cu_die, "")
            print(f"Searching CU {i}: {cu_name}")
            
            matches = self._find_hierarchy_matches(cu_die, hierarchy, 0)
            print(f"  Found {len(matches)} matches")
            
            for match in matches:
                future_struct = self._find_sibling_future_struct(match)
                print(f"    Match: {safe_DIE_name(match, '')} -> Future: {safe_DIE_name(future_struct, '') if future_struct else 'None'}")


    def _is_target_async_function(self, die):
        """Check if this DIE is the target async function we're looking for"""
        tag = die.tag if hasattr(die, 'tag') else ""
        name = safe_DIE_name(die, "")
        
        return (tag == 'DW_TAG_subprogram' and 
                '{async_fn#0}' in name)
    
    def is_async_function_die(die):
        """Check if DIE represents an async function"""
        name = safe_DIE_name(die, "")
        tag = die.tag if hasattr(die, 'tag') else ""
        
        return (tag == 'DW_TAG_subprogram' and 
                '{async_fn#0}' in name)

    def is_future_struct_die(die):
        """Check if DIE represents a future structure"""
        name = safe_DIE_name(die, "")
        tag = die.tag if hasattr(die, 'tag') else ""
        
        return (tag == 'DW_TAG_structure_type' and 
                ('async_fn_env#0' in name or 
                'async_fn_env' in name))

    def is_namespace_die(die):
        """Check if DIE is a namespace"""
        tag = die.tag if hasattr(die, 'tag') else ""
        return tag == 'DW_TAG_namespace'
    
    def search_hierarchy_in_cu(self, cu_die, hierarchy, depth=0):
        """
        Search for a hierarchy of names in a compilation unit.
        
        Args:
            cu_die (DIE): The compilation unit to search in.
            hierarchy (list): List of names to match in order.
            depth (int): Current depth in the hierarchy.
        
        Returns:
            list: Matching DIEs that match the full hierarchy.
        """
        if depth >= len(hierarchy):
            return []
        
        current_name = hierarchy[depth]
        matches = []
        
        # Load children if not already loaded
        load_children(cu_die, True)
        
        # Iterate through all children of the current DIE
        for child_die in cu_die._children:
            child_name = safe_DIE_name(child_die, "")
            
            # Check if this child matches the current hierarchy level
            if child_name == current_name:
                if depth == len(hierarchy) - 1:
                    # We've matched the full hierarchy - this is a final match
                    matches.append(child_die)
                else:
                    # Continue searching deeper in this subtree
                    sub_matches = self.search_hierarchy_in_cu(child_die, hierarchy, depth + 1)
                    matches.extend(sub_matches)
            
            # Also recursively search in child's subtree even if name doesn't match
            # This handles nested namespace structures caused by, for example, {impl#0}
            if child_die.has_children:
                sub_matches = self.search_hierarchy_in_cu(child_die, hierarchy, depth)
                matches.extend(sub_matches)
        
        return matches

    def _find_sibling_future_struct(self, async_fn_die):
        """
        Find the corresponding future struct for an async function DIE.
        
        According to dwarf_analyzer.md line 512, we need to look for sibling
        structures with names like {async_fn_env#0} that represent the future.
        
        Args:
            async_fn_die (DIE): The async function DIE to find the future struct for
            
        Returns:
            DIE or None: The future struct DIE, or None if not found
        """
        if not async_fn_die or not hasattr(async_fn_die, '_parent') or not async_fn_die._parent:
            return None
        
        parent_die = async_fn_die._parent
        
        # Load parent's children to search for siblings
        load_children(parent_die, True)
        
        # Look for sibling structures that could be the future
        for sibling in parent_die._children:
            sibling_name = safe_DIE_name(sibling, "")
            sibling_tag = sibling.tag if hasattr(sibling, 'tag') else ""
            
            # Check if this sibling is a future struct
            if (sibling_tag == 'DW_TAG_structure_type' and
                ('{async_fn_env#0}' in sibling_name or 
                 'async_fn_env' in sibling_name)):
                return sibling
        
        return None

    def pollToFuture(self, poll_fn_name):
        """
        Convert a polling function name to a future function name.
        This is a placeholder implementation and should be replaced with
        the actual conversion logic.
        """
        # turn poll_fn_name into hierarchy
        components = self.parse_poll_function_hierarchy(poll_fn_name)
        if not components:
            print(f"[rust-future-tracing] ERROR: Unable to parse poll function name: {poll_fn_name}")
            return None
        
        
        
        # Get the DWARF tree
        tree = self._get_tree_safely()
        if not tree:
            return None  # Not initialized

        # Search for the poll function across all compilation units
        all_matches = []
        for cu_die in tree.top_dies:
            matches = self.search_hierarchy_in_cu(cu_die, components, 0)
            all_matches.extend(matches)
        
        if not all_matches:
            print(f"[rust-future-tracing] No matches found for hierarchy: {components}")
            return None
        
        # For each match, try to find the corresponding future struct
        future_structs = []
        for match in all_matches:
            future_struct = self._find_sibling_future_struct(match)
            if future_struct:
                future_structs.append(future_struct)
        
        if not future_structs:
            print(f"[rust-future-tracing] No future structs found for poll function: {poll_fn_name}")
            return None
        
        # Return the name of the first future struct found
        future_name = safe_DIE_name(future_structs[0], "")
        print(f"[rust-future-tracing] Mapped {poll_fn_name} -> {future_name}")
        return future_name

    def invoke(self, arg, from_tty):
        if not plugin:
            print("[gdb_debugger] No plugin loaded. Cannot start.")
            return

        print("[gdb_debugger] Setting instrumentation points...")
        for point in plugin.instrument_points():
            try:
                EntryBreakpoint(point["symbol"], point["entry_tracers"], point["exit_tracers"])
                print(f"  - Breakpoint set for {point['symbol']}")
            except gdb.error as e:
                print(f"  - ERROR setting breakpoint for {point['symbol']}: {e}")
        
        print("\n[gdb_debugger] Instrumentation complete. Run your program.")
        print("Use 'dump-async-data' after execution to see the report.")

class InspectAsync(gdb.Command):
    """
    Inspects the current state of the async runtime and prints a detailed
    snapshot, including worker threads and their states.
    """
    def __init__(self):
        super().__init__("inspect-async", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        pass


class DumpAsyncData(gdb.Command):
    """GDB command to process and dump the collected trace data."""
    def __init__(self):
        super().__init__("dump-async-data", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not plugin:
            print("[gdb_debugger] No plugin loaded.")
            return
        
        print("[gdb_debugger] Processing collected data...")
        plugin.process_data(traced_data)
