import gdb
import os
import sys
import importlib
import re
from typing import Optional, List, Tuple, Union

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
from elftools.dwarf.die import DIE
from elftools.dwarf.compileunit import CompileUnit



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

# Make bp_commands available in GDB's global namespace
import __main__
__main__.bp_commands = bp_commands

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

# Make run_tracers available in GDB's global namespace since it's called by the instrumentation framework
__main__.run_tracers = run_tracers

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
        print(f"[rust-future-tracing] Setting up entry breakpoint for: {symbol}")
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

    def parse_future_struct_hierarchy(self, future_struct_name):
        """
        Parse a future struct name into hierarchical components for DWARF analysis.
        
        Args:
            future_struct_name (str): Future struct name like "reqwest::get::{async_fn_env#0}<&str>"
            
        Returns:
            list: Hierarchical namespace components
            
        Examples:
            "reqwest::get::{async_fn_env#0}<&str>" -> ["reqwest", "get", "{async_fn_env#0}<&str>"]
        """
        import re
        
        # Remove any "static " prefix if present
        cleaned_name = re.sub(r'^static\s+', '', future_struct_name)
        
        # Split by "::" but be careful not to split inside angle brackets
        components = []
        current_component = ""
        bracket_depth = 0
        
        i = 0
        while i < len(cleaned_name):
            if cleaned_name[i] == '<':
                bracket_depth += 1
                current_component += cleaned_name[i]
            elif cleaned_name[i] == '>':
                bracket_depth -= 1
                current_component += cleaned_name[i]
            elif cleaned_name[i:i+2] == '::' and bracket_depth == 0:
                # Only split on :: when we're not inside angle brackets
                if current_component.strip():
                    components.append(current_component.strip())
                current_component = ""
                i += 1  # Skip the second ':'
            else:
                current_component += cleaned_name[i]
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
    
    def is_async_function_die(self, die) -> bool:
        """
        Check if DIE represents an async function.
        
        Args:
            die: DWARF DIE object with .offset attribute for getting DIE offset
            
        Returns:
            bool: True if this is an async function DIE
            
        Note:
            DIE offset can be accessed via: die.offset (returns int)
        """
        name = safe_DIE_name(die, "")
        tag = die.tag if hasattr(die, 'tag') else ""
        
        return (tag == 'DW_TAG_subprogram' and 
                '{async_fn#' in name)  # TODO: 1. handle {impl#?} 2. in rare cases this might not strict enough, should use regex to match {async_fn#\d+} or {impl#\d+}

    def is_future_struct_die(self, die) -> bool:
        """
        Check if DIE represents a future structure.
        
        Args:
            die: DWARF DIE object with .offset attribute for getting DIE offset
            
        Returns:
            bool: True if this is a future struct DIE
            
        Note:
            DIE offset can be accessed via: die.offset (returns int)
        """
        name = safe_DIE_name(die, "")
        tag = die.tag if hasattr(die, 'tag') else ""
        
        return (tag == 'DW_TAG_structure_type' and 
                ('{async_fn_env#' in name)) # TODO: 1. handle {impl#?} 2. in rare cases this might not strict enough, should use regex to match {async_fn_env#\d+} or {impl#\d+}

    def is_namespace_die(die):
        """Check if DIE is a namespace"""
        tag = die.tag if hasattr(die, 'tag') else ""
        return tag == 'DW_TAG_namespace'
    
    def search_poll_hierarchy_in_cu(self, cu_die, hierarchy, depth=0):
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
            child_tag = child_die.tag if hasattr(child_die, 'tag') else ""
            
            # Check if this child matches the current hierarchy level
            if child_name == current_name:
                if depth == len(hierarchy) - 1:
                    # We've matched the full hierarchy - this is a final match
                    # check if it's an function (not necessarily an async function)
                    if child_tag == 'DW_TAG_subprogram':
                        matches.append(child_die)
                else:
                    # Continue searching deeper in this subtree
                    sub_matches = self.search_poll_hierarchy_in_cu(child_die, hierarchy, depth + 1)
                    matches.extend(sub_matches)
            
            # Also recursively search in child's subtree even if name doesn't match
            # This handles nested namespace structures caused by, for example, {impl#0}
            if child_die.has_children:
                sub_matches = self.search_poll_hierarchy_in_cu(child_die, hierarchy, depth)
                matches.extend(sub_matches)
        
        return matches

    def search_future_struct_in_cu(self, cu_die, hierarchy, depth=0):
        """
        Search for a future struct hierarchy in a compilation unit.
        
        Args:
            cu_die (DIE): The compilation unit to search in
            hierarchy (list): List of names to match in order
            depth (int): Current depth in the hierarchy
            
        Returns:
            list: Matching future struct DIEs
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
            child_tag = child_die.tag if hasattr(child_die, 'tag') else ""
            
            # Check if this child matches the current hierarchy level
            if child_name == current_name:
                if depth == len(hierarchy) - 1:
                    # We've matched the full hierarchy - check if it's a structure_type
                    if child_tag == 'DW_TAG_structure_type':
                        matches.append(child_die)
                else:
                    # Continue searching deeper in this subtree
                    sub_matches = self.search_future_struct_in_cu(child_die, hierarchy, depth + 1)
                    matches.extend(sub_matches)
            
            # Also recursively search in child's subtree even if name doesn't match
            # This handles nested namespace structures
            if child_die.has_children:
                sub_matches = self.search_future_struct_in_cu(child_die, hierarchy, depth)
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
            sibling_counter = None # the number after async_fn_env#
            sibling_counter_result = re.search(r'\{async_fn_env#(\d+)\}', sibling_name)
            if sibling_counter_result:
                sibling_counter = sibling_counter_result.group(1)
            sibling_tag = sibling.tag if hasattr(sibling, 'tag') else ""
            
            # Check if this sibling is a future struct
            # the sibling counter should match the async_fn_env# counter too
            if (sibling_tag == 'DW_TAG_structure_type' and
                '{async_fn_env#' + sibling_counter + '}' in sibling_name):
                    return sibling

        print(f"[rust-future-tracing] No future struct found for function: {safe_DIE_name(async_fn_die, '')}")
        return None
    
    def _find_sibling_poll_function(self, future_struct_die):
        """
        Find the corresponding poll function for a future struct DIE.
        
        According to dwarf_analyzer.md, we need to look for sibling
        subprograms with names like {async_fn#0} that represent the poll function.
        
        Args:
            future_struct_die (DIE): The future struct DIE to find the poll function for
            
        Returns:
            DIE or None: The poll function DIE, or None if not found
        """
        if not future_struct_die or not hasattr(future_struct_die, '_parent') or not future_struct_die._parent:
            return None
        
        parent_die = future_struct_die._parent
        
        # Load parent's children to search for siblings
        load_children(parent_die, True)
        
        # Look for sibling subprograms that could be the poll function
        for sibling in parent_die._children:
            sibling_name = safe_DIE_name(sibling, "")
            sibling_counter = None # the number after async_fn#0
            sibling_counter_result = re.search(r'\{async_fn#(\d+)\}', sibling_name)
            if sibling_counter_result:
                sibling_counter = sibling_counter_result.group(1)
            sibling_tag = sibling.tag if hasattr(sibling, 'tag') else ""
            
            # Check if this sibling is a poll function
            # the sibling counter should match the async_fn# counter too
            # TODO: we assume the poll function is always a subprogram
            # and has a name like {async_fn#0} or {impl#N}
            # This is a simplification, but it matches the common patterns in Rust async code.
            if (sibling_tag == 'DW_TAG_subprogram' and
                ('{async_fn#' + sibling_counter + '}' in sibling_name)):
                return sibling

        print(f"[rust-future-tracing] No poll function found for future struct: {safe_DIE_name(future_struct_die, '')}")
        return None
    def dieToFullName(self, die: DIE) -> str:
        """
        Convert a DIE to its full name, including namespace.
        
        Args:
            die (DIE type): The DIE object to convert
            
        Returns:
            str: Full name of the DIE with namespace
        """
        if not die:
            return ""
        
        # Get the name of the current DIE
        current_name = safe_DIE_name(die, "")
        if not current_name:
            return ""
        
        # Build the full name by traversing up the parent hierarchy
        name_parts = []
        current_die = die
        
        while current_die:
            current_die_name = safe_DIE_name(current_die, "")
            if current_die_name:
                # Only include meaningful names (skip empty names and compilation unit names)
                current_tag = current_die.tag if hasattr(current_die, 'tag') else ""
                
                # Skip compilation unit names as they're usually file paths
                if current_tag != 'DW_TAG_compile_unit':
                    name_parts.append(current_die_name)
            
            # Move to parent DIE
            if hasattr(current_die, '_parent') and current_die._parent:
                current_die = current_die._parent
            else:
                break
        
        # Reverse the list since we built it from child to parent
        name_parts.reverse()
        
        # Join with "::" to create the full qualified name
        if name_parts:
            return "::".join(name_parts)
        else:
            return current_name

    def _build_poll_function_name(self, poll_die, future_struct_name):
        """
        Build the full poll function name from a poll DIE and the original future struct name.
        
        Args:
            poll_die (DIE): The poll function DIE
            future_struct_name (str): Original future struct name for context
            
        Returns:
            str: Full poll function name with namespace
        """
        poll_name = safe_DIE_name(poll_die, "")
        
        # Parse the original future struct name to get the namespace path
        hierarchy = self.parse_future_struct_hierarchy(future_struct_name)
        
        if len(hierarchy) >= 2:
            # Replace the last component ({async_fn_env#0}) with the poll function name
            namespace_parts = hierarchy[:-1]  # Everything except the last part
            
            # Build the full poll function name
            full_name = "::".join(namespace_parts) + "::" + poll_name
            return full_name
        
        return poll_name

    def _build_future_struct_name(self, future_die, poll_fn_name):
        """
        Build the full future struct name from a future DIE and the original poll function name.
        
        Args:
            future_die (DIE): The future struct DIE
            poll_fn_name (str): Original poll function name for context
            
        Returns:
            str: Full future struct name with namespace
        """
        future_name = safe_DIE_name(future_die, "")
        
        # Parse the original poll function name to get the namespace path
        hierarchy = self.parse_poll_function_hierarchy(poll_fn_name)
        
        if len(hierarchy) >= 2:
            # Replace the last component ({async_fn#0}) with the future struct name
            namespace_parts = hierarchy[:-1]  # Everything except the last part
            
            # Build the full future struct name
            full_name = "::".join(namespace_parts) + "::" + future_name
            return full_name
        
        return future_name
    
    def find_poll_function_in_dwarf_tree(self, poll_fn_name: str) -> List[Tuple[object, int]]:
        """
        Step 1: Find poll function DIEs in DWARF tree.
        
        This is the decomposed first part of pollToFuture that searches for poll functions
        in the DWARF tree and returns both the DIE and its offset.
        
        Args:
            poll_fn_name (str): Poll function name from GDB
            
        Returns:
            List[Tuple[DIE, int]]: List of (DIE object, DIE offset) tuples for found poll functions
        """
        # Parse poll function name into hierarchy
        components = self.parse_poll_function_hierarchy(poll_fn_name)
        if not components:
            print(f"[rust-future-tracing] ERROR: Unable to parse poll function name: {poll_fn_name}")
            return []
        
        # Get the DWARF tree
        tree = self._get_tree_safely()
        if not tree:
            return []  # Not initialized

        # Search for the poll function across all compilation units
        all_matches = []
        for cu_die in tree.top_dies:
            matches = self.search_poll_hierarchy_in_cu(cu_die, components, 0)
            # Convert matches to (DIE, offset) tuples
            for match in matches:
                all_matches.append((match, match.offset))
        
        if not all_matches:
            print(f"[rust-future-tracing] No matches found for hierarchy: {components}")
            return []
        
        return all_matches
    
    def find_future_struct_for_poll_function(self, poll_die: object, poll_offset: int) -> Optional[Tuple[object, int]]:
        """
        Step 2: Find future struct DIE for a given poll function DIE.
        
        This is the decomposed second part of pollToFuture that finds the corresponding
        future struct and returns both the DIE and its offset.
        
        Args:
            poll_die: Poll function DIE object
            poll_offset (int): Poll function DIE offset
            
        Returns:
            Optional[Tuple[DIE, int]]: (future struct DIE, future struct offset) or None if not found
        """
        future_struct = self._find_sibling_future_struct(poll_die)
        if future_struct:
            return (future_struct, future_struct.offset)
        
        print(f"[rust-future-tracing] No future struct found for poll function at offset: {poll_offset}")
        return None

    def pollToFuture(self, poll_fn_name: str) -> Optional[str]:
        """
        Convert a polling function name to a future function name.
        
        This method now uses the decomposed approach for better code reuse and abstraction.
        
        Args:
            poll_fn_name (str): Poll function name from GDB
            
        Returns:
            Optional[str]: Future struct name, or None if not found
            
        Note:
            This method finds DIE objects with .offset attribute (int) for DIE offsets
        """
        # Step 1: Find poll function DIEs in DWARF tree
        poll_matches = self.find_poll_function_in_dwarf_tree(poll_fn_name)
        if not poll_matches:
            return None
        
        # Step 2: Find corresponding future structs
        future_structs = []
        for poll_die, poll_offset in poll_matches:
            future_result = self.find_future_struct_for_poll_function(poll_die, poll_offset)
            if future_result:
                future_structs.append(future_result)
        
        if not future_structs:
            print(f"[rust-future-tracing] No future structs found for poll function: {poll_fn_name}")
            return None
        
        # Return the full name of the first future struct found return others if any
        if len(future_structs) > 1:
            print(f"[rust-future-tracing] Warning: Multiple future structs found for poll function {poll_fn_name}, the following are ignored:")
            for future_die, future_offset in future_structs[1:]:
                print(f"  - {safe_DIE_name(future_die, '')} (DIE offset: {future_offset})")
        # Use the first match as the primary result
        future_die, future_offset = future_structs[0]
        future_name = self._build_future_struct_name(future_die, poll_fn_name)
        print(f"[rust-future-tracing] Mapped {poll_fn_name} -> {future_name} (DIE offset: {future_offset})")
        return future_name

    def find_future_struct_in_dwarf_tree(self, future_struct_name: str) -> List[Tuple[object, int]]:
        """
        Step 1: Find future struct DIEs in DWARF tree.
        
        This is the decomposed first part of futureToPoll that searches for future structs
        in the DWARF tree and returns both the DIE and its offset.
        
        Args:
            future_struct_name (str): Future struct name like "reqwest::get::{async_fn_env#0}<&str>"
            
        Returns:
            List[Tuple[DIE, int]]: List of (DIE object, DIE offset) tuples for found future structs
        """
        # Parse future struct name into hierarchy
        components = self.parse_future_struct_hierarchy(future_struct_name)
        if not components:
            print(f"[rust-future-tracing] ERROR: Unable to parse future struct name: {future_struct_name}")
            return []
        
        # Validate that this looks like a future struct (should end with {async_fn_env#0})
        if not any('{async_fn_env#0}' in comp for comp in components):
            print(f"[rust-future-tracing] ERROR: Not a valid future struct name (missing async_fn_env): {future_struct_name}")
            return []
        
        # Get the DWARF tree
        tree = self._get_tree_safely()
        if not tree:
            return []  # Not initialized

        # Search for the future struct across all compilation units
        all_matches = []
        for cu_die in tree.top_dies:
            matches = self.search_future_struct_in_cu(cu_die, components, 0)
            # Convert matches to (DIE, offset) tuples
            for match in matches:
                all_matches.append((match, match.offset))
        
        if not all_matches:
            print(f"[rust-future-tracing] No future struct matches found for hierarchy: {components}")
            return []
        
        return all_matches
    
    def find_poll_function_for_future_struct(self, future_die: object, future_offset: int) -> Optional[Tuple[object, int]]:
        """
        Step 2: Find poll function DIE for a given future struct DIE.
        
        This is the decomposed second part of futureToPoll that finds the corresponding
        poll function and returns both the DIE and its offset.
        
        Args:
            future_die: Future struct DIE object
            future_offset (int): Future struct DIE offset
            
        Returns:
            Optional[Tuple[DIE, int]]: (poll function DIE, poll function offset) or None if not found
        """
        poll_function = self._find_sibling_poll_function(future_die)
        if poll_function:
            return (poll_function, poll_function.offset)
        
        print(f"[rust-future-tracing] No poll function found for future struct at offset: {future_offset}")
        return None

    def futureToPoll(self, future_struct_name: str) -> Optional[str]:
        """
        Convert a future struct name to its corresponding polling function name.
        
        This implements the reverse mapping described in dwarf_analyzer.md lines 513-520:
        "future 结构体 -> poll 函数名"
        
        This method now uses the decomposed approach for better code reuse and abstraction.
        
        Args:
            future_struct_name (str): Future struct name like "reqwest::get::{async_fn_env#0}<&str>"
            
        Returns:
            Optional[str]: The corresponding poll function name, or None if not found
            
        Examples:
            "reqwest::get::{async_fn_env#0}<&str>" -> "reqwest::get::{async_fn#0}<&str>"
            
        Note:
            This method finds DIE objects with .offset attribute (int) for DIE offsets
        """
        # Step 1: Find future struct DIEs in DWARF tree
        future_matches = self.find_future_struct_in_dwarf_tree(future_struct_name)
        if not future_matches:
            return None
        
        # Step 2: Find corresponding poll functions
        poll_functions = []
        for future_die, future_offset in future_matches:
            poll_result = self.find_poll_function_for_future_struct(future_die, future_offset)
            if poll_result:
                poll_functions.append(poll_result)
        
        if not poll_functions:
            print(f"[rust-future-tracing] No poll functions found for future struct: {future_struct_name}")
            return None
        
        # Return the first poll function foundreport others if any
        if len(poll_functions) > 1:
            print(f"[rust-future-tracing] Warning: Multiple poll functions found for future struct {future_struct_name}, the following are ignored:")
            for poll_die, poll_offset in poll_functions[1:]:
                print(f"  - {safe_DIE_name(poll_die, '')} (DIE offset: {poll_offset})")
        # Use the first match as the primary result
        poll_die, poll_offset = poll_functions[0]
        poll_name = self._build_poll_function_name(poll_die, future_struct_name)
        print(f"[rust-future-tracing] Mapped {future_struct_name} -> {poll_name} (DIE offset: {poll_offset})")
        return poll_name

    def _read_interesting_functions_and_convert_to_futures(self):
        """
        Read poll_map.json for user-selected interesting functions and convert them to futures.
        
        Returns:
            list: List of interesting future struct names converted from poll functions
        """
        import json
        import os
        
        # Look for poll_map.json in results directory
        poll_map_path = os.path.join(os.getcwd(), "results", "poll_map.json")
        if not os.path.exists(poll_map_path):
            print(f"[rust-future-tracing] Error: poll_map.json not found at {poll_map_path}")
            return []
        
        try:
            with open(poll_map_path, 'r') as f:
                poll_map = json.load(f)
        except Exception as e:
            print(f"[rust-future-tracing] Error reading poll_map.json: {e}")
            return []
        
        # Find functions marked with async_backtrace: true
        interesting_poll_functions = []
        for file_path, function_data in poll_map.items():
            if function_data.get("async_backtrace", False):
                fn_name = function_data.get("fn_name", "")
                if fn_name:
                    interesting_poll_functions.append(fn_name)
                    print(f"[rust-future-tracing] Found interesting poll function: {fn_name}")
        
        if not interesting_poll_functions:
            print("[rust-future-tracing] No functions marked with 'async_backtrace': true")
            return []
        
        # Convert poll functions to future structs using pollToFuture
        interesting_futures = []
        for poll_fn in interesting_poll_functions:
            try:
                future_struct = self.pollToFuture(poll_fn)
                if future_struct:
                    interesting_futures.append(future_struct)
                else:
                    print(f"[rust-future-tracing] Warning: Could not convert poll function to future: {poll_fn}")
            except Exception as e:
                print(f"[rust-future-tracing] Error converting {poll_fn}: {e}")
        
        return interesting_futures

    def offsetToDIE(self, die_offset: int) -> Optional[Tuple[object, str]]:
        """
        Convert a DIE offset to the corresponding DIE object and determine its type.
        
        This method is referenced in the document for Step 3 implementation.
        It uses the DWARF tree's existing API to find a DIE by offset and classify it.
        
        Args:
            die_offset (int): DIE offset to look up
            
        Returns:
            Optional[Tuple[DIE, str]]: (DIE object, DIE type) where DIE type is one of:
                - "async_function" for async function DIEs
                - "future_struct" for future struct DIEs  
                - "other" for other types of DIEs
                Returns None if DIE not found
        """
        tree = self._get_tree_safely()
        if not tree:
            return None
        
        # Use the tree model's find_offset method (similar to on_byoffset in dwarf/__main__.py)
        try:
            index = tree.find_offset(die_offset)
            if not index:
                print(f"[rust-future-tracing] DIE offset {die_offset} not found in DWARF tree")
                return None
            
            # Get the DIE object from the index
            die = index.internalPointer()
            if not die:
                print(f"[rust-future-tracing] No DIE object found at offset {die_offset}")
                return None
            
            # Classify the DIE type
            if self.is_async_function_die(die):
                return (die, "async_function")
            elif self.is_future_struct_die(die):
                return (die, "future_struct")
            else:
                return (die, "other")
                
        except Exception as e:
            print(f"[rust-future-tracing] Error looking up DIE at offset {die_offset}: {e}")
            return None

    def convert_interesting_futures_to_die_offsets(self, interesting_futures: List[str]) -> List[int]:
        """
        Convert interesting future names to their DIE offsets for dependency lookup.
        
        This is the small step added after Step 1 as mentioned in the document:
        "在'第一步'后添加一个小步骤：把'感兴趣future'转换为 DIE offset 供第二步查询"
        
        Args:
            interesting_futures: List of future struct names like ["reqwest::get::{async_fn_env#0}<&str>"]
            
        Returns:
            List[int]: List of DIE offsets corresponding to the future structs
        """
        die_offsets = []
        
        for future_name in interesting_futures:
            print(f"[rust-future-tracing] Converting future to DIE offset: {future_name}")
            
            # Use our decomposed method from Step 2 to find the future struct DIE
            future_matches = self.find_future_struct_in_dwarf_tree(future_name)
            
            if future_matches:
                future_offsets = []
                for die, offset in future_matches:
                    poll_function = self._find_sibling_poll_function(die)
                    if poll_function:
                        future_offsets.append(offset)
                if not future_offsets:
                    print(f"[rust-future-tracing] WARNING: No poll function found for future: {future_name}")
                    continue
                # Return the first found offset as the representative DIE offset, report others if any
                future_offset = future_offsets[0]
                if len(future_offsets) > 1:
                    print(f"[rust-future-tracing] Warning: Multiple poll functions found for future {future_name}, the following are ignored:")
                    for offset in future_offsets[1:]:
                        print(f"  - DIE offset: {offset}")
                # Append the first found offset to the list
                die_offsets.append(future_offset)
                print(f"[rust-future-tracing] Mapped {future_name} -> DIE offset: {future_offset}")
            else:
                print(f"[rust-future-tracing] WARNING: Could not find DIE offset for future: {future_name}")
        
        return die_offsets

    def load_async_dependencies(self) -> Optional[dict]:
        """
        Load async dependency information from async_dependencies.json.
        
        Returns:
            Optional[dict]: Parsed JSON data or None if loading failed
        """
        import json
        import os
        
        # Look for async_dependencies.json in results directory
        deps_path = os.path.join(os.getcwd(), "results", "async_dependencies.json")
        if not os.path.exists(deps_path):
            print(f"[rust-future-tracing] ERROR: async_dependencies.json not found at {deps_path}")
            return None
        
        try:
            with open(deps_path, 'r') as f:
                deps_data = json.load(f)
            print(f"[rust-future-tracing] Loaded async dependencies from {deps_path}")
            return deps_data
        except Exception as e:
            print(f"[rust-future-tracing] ERROR loading async_dependencies.json: {e}")
            return None

    def expand_future_dependencies(self, interesting_die_offsets: List[int]) -> dict:
        """
        Expand future dependencies in both ancestor and descendant directions.
        
        As described in the document:
        - Ancestor expansion ("往长辈方向扩展") finds the bottom of async call stacks and coroutine boundaries
        - Descendant expansion ("往子孙方向扩展") finds the top of async call stacks
        
        Args:
            interesting_die_offsets: List of DIE offsets for interesting futures
            
        Returns:
            dict: Expanded dependency information with structure:
                {
                    "expanded_offsets": List[int],  # All expanded DIE offsets
                    "ancestors": {offset: [ancestor_offsets]},  # Ancestor relationships
                    "descendants": {offset: [descendant_offsets]},  # Descendant relationships
                    "coroutines": List[int],  # Bottom-level futures (coroutines)
                    "call_stack_tops": List[int]  # Top-level futures
                }
        """
        # Load dependency data
        deps_data = self.load_async_dependencies()
        if not deps_data:
            return {"expanded_offsets": [], "ancestors": {}, "descendants": {}, "coroutines": [], "call_stack_tops": []}
        
        dependency_tree = deps_data.get("dependency_tree", {})
        
        # Convert DIE offsets to hex strings (JSON keys are strings)
        interesting_hex_offsets = [hex(offset)[2:] for offset in interesting_die_offsets]
        
        expanded_offsets = set(interesting_die_offsets)
        ancestors = {}
        descendants = {}
        
        # Helper function to perform DFS expansion
        def expand_dependencies(current_hex_offset: str, direction: str, visited: set):
            if current_hex_offset in visited:
                return []
            
            visited.add(current_hex_offset)
            current_offset = int(current_hex_offset, 16)
            
            if direction == "ancestors":
                # Find all DIEs that depend on this one (this DIE is in their dependency list)
                related_offsets = []
                for die_hex, deps in dependency_tree.items():
                    if current_hex_offset in deps:
                        related_offsets.append(int(die_hex, 16))
                
                if current_offset not in ancestors:
                    ancestors[current_offset] = []
                
                for related_offset in related_offsets:
                    ancestors[current_offset].append(related_offset)
                    expanded_offsets.add(related_offset)
                    # Recursively expand ancestors
                    expand_dependencies(hex(related_offset)[2:], direction, visited.copy())
                    
            elif direction == "descendants":
                # Find all DIEs that this one depends on
                deps = dependency_tree.get(current_hex_offset, [])
                descendant_offsets = [int(dep, 16) for dep in deps]
                
                if current_offset not in descendants:
                    descendants[current_offset] = []
                
                for desc_offset in descendant_offsets:
                    descendants[current_offset].append(desc_offset)
                    expanded_offsets.add(desc_offset)
                    # Recursively expand descendants
                    expand_dependencies(hex(desc_offset)[2:], direction, visited.copy())
        
        # Expand in both directions for each interesting future
        for hex_offset in interesting_hex_offsets:
            print(f"[rust-future-tracing] Expanding dependencies for DIE offset: 0x{hex_offset}")
            
            # Expand ancestors (find what depends on this future)
            expand_dependencies(hex_offset, "ancestors", set())
            
            # Expand descendants (find what this future depends on)
            expand_dependencies(hex_offset, "descendants", set())
        
        # Identify coroutines (futures with no ancestors - bottom of call stack)
        coroutines = []
        for offset in expanded_offsets:
            if offset not in ancestors or not ancestors[offset]:
                coroutines.append(offset)
        
        # Identify call stack tops (futures with no descendants)
        call_stack_tops = []
        for offset in expanded_offsets:
            if offset not in descendants or not descendants[offset]:
                call_stack_tops.append(offset)
        
        result = {
            "expanded_offsets": list(expanded_offsets),
            "ancestors": ancestors,
            "descendants": descendants,
            "coroutines": coroutines,
            "call_stack_tops": call_stack_tops
        }
        
        print(f"[rust-future-tracing] Expansion complete:")
        print(f"  - Total expanded DIE offsets: {len(expanded_offsets)}")
        print(f"  - Coroutines (bottom-level): {len(coroutines)}")
        print(f"  - Call stack tops: {len(call_stack_tops)}")
        
        return result

    def validate_expanded_futures_with_die_tree(self, expanded_info: dict) -> dict:
        """
        Validate expanded futures using DIE tree data structures instead of offset_to_name.
        
        As mentioned in the document: "不要使用 async_dependencies.json 内部的 DIE offset - 函数/结构体名 对照表
        (offset_to_name) 那个对照表是从 objdump 的输出中提取出来的，所以函数名/结构体名不一定和 elftools 的解析结果一致"
        
        Args:
            expanded_info: Result from expand_future_dependencies
            
        Returns:
            dict: Validated expansion info with DIE type classification
        """
        validated_futures = {
            "async_functions": [],
            "future_structs": [],
            "other_dies": [],
            "invalid_offsets": []
        }
        
        for die_offset in expanded_info["expanded_offsets"]:
            # Use offsetToDIE method to get DIE and classify its type
            die_result = self.offsetToDIE(die_offset)
            
            if die_result:
                die_obj, die_type = die_result
                
                if die_type == "async_function":
                    validated_futures["async_functions"].append({
                        "offset": die_offset,
                        "die": die_obj,
                        "name": safe_DIE_name(die_obj, f"<unknown_async_fn_{die_offset}>")
                    })
                elif die_type == "future_struct":
                    validated_futures["future_structs"].append({
                        "offset": die_offset,
                        "die": die_obj,
                        "name": safe_DIE_name(die_obj, f"<unknown_future_{die_offset}>")
                    })
                else:
                    validated_futures["other_dies"].append({
                        "offset": die_offset,
                        "die": die_obj,
                        "type": die_type,
                        "name": safe_DIE_name(die_obj, f"<unknown_{die_offset}>")
                    })
            else:
                validated_futures["invalid_offsets"].append(die_offset)
                print(f"[rust-future-tracing] WARNING: Invalid DIE offset during validation: {die_offset}")
        
        print(f"[rust-future-tracing] Validation complete:")
        print(f"  - Async functions: {len(validated_futures['async_functions'])}")
        print(f"  - Future structs: {len(validated_futures['future_structs'])}")
        print(f"  - Other DIEs: {len(validated_futures['other_dies'])}")
        print(f"  - Invalid offsets: {len(validated_futures['invalid_offsets'])}")
        
        return validated_futures

    def perform_future_expansion(self, interesting_futures: List[str]) -> dict:
        """
        Complete Step 3: Perform future expansion on interesting futures.
        
        This method orchestrates the entire Step 3 process:
        1. Convert interesting futures to DIE offsets
        2. Load async dependencies
        3. Expand dependencies in both directions
        4. Validate using DIE tree (not offset_to_name)
        
        Args:
            interesting_futures: List of interesting future names from Step 1
            
        Returns:
            dict: Complete expansion and validation results
        """
        print("[rust-future-tracing] === Step 3: Performing future expansion ===")
        
        # Sub-step: Convert interesting futures to DIE offsets
        print("[rust-future-tracing] Converting interesting futures to DIE offsets...")
        interesting_die_offsets = self.convert_interesting_futures_to_die_offsets(interesting_futures)
        
        if not interesting_die_offsets:
            print("[rust-future-tracing] No DIE offsets found for interesting futures")
            return {}
        
        # Main expansion process
        print("[rust-future-tracing] Expanding future dependencies...")
        expanded_info = self.expand_future_dependencies(interesting_die_offsets)
        
        # Validation using DIE tree
        print("[rust-future-tracing] Validating expanded futures with DIE tree...")
        validated_futures = self.validate_expanded_futures_with_die_tree(expanded_info)
        
        # Combine results
        result = {
            "original_futures": interesting_futures,
            "interesting_die_offsets": interesting_die_offsets,
            "expansion_info": expanded_info,
            "validated_futures": validated_futures
        }
        
        print("[rust-future-tracing] === Step 3 complete ===")
        return result

    def convert_expanded_futures_to_poll_functions(self, expansion_results: dict) -> List[str]:
        """
        Step 4: Convert expanded future list to corresponding poll functions.
        
        This implements Step 4 from the document: "利用 pollToFuture 和 FutureToPoll 功能，
        获得扩展后的 future 列表对应的 poll 函数"
        
        Args:
            expansion_results: Results from Step 3 future expansion
            
        Returns:
            List[str]: List of poll function names corresponding to expanded futures
        """
        print("[rust-future-tracing] === Step 4: Converting expanded futures to poll functions ===")
        
        validated_futures = expansion_results.get("validated_futures", {})
        future_structs = validated_futures.get("future_structs", [])
        
        if not future_structs:
            print("[rust-future-tracing] No future structs found in expansion results")
            return []
        
        poll_functions = []
        
        # Convert each expanded future struct to its corresponding poll function
        for future_info in future_structs:
            future_offset = future_info["offset"]
            future_die = future_info["die"]
            
            # future_name = future_info["name"] # this is the shortened version of the future struct name that only contains the last part
            future_name = safe_DIE_name(future_die, f"<unknown_future_{future_offset}>")

            
            print(f"[rust-future-tracing] Converting future to poll function: {future_name} (offset: {future_offset})")
            
            # Use our decomposed method from Step 2 to find the corresponding poll function
            poll_result = self.find_poll_function_for_future_struct(future_die, future_offset)
            
            if poll_result:
                poll_die, poll_offset = poll_result
                # poll_name = self._build_poll_function_name(poll_die, future_name)
                poll_name = self.dieToFullName(poll_die)
                if not poll_name:
                    print(f"[rust-future-tracing] WARNING: Could not build poll function name for future: {future_name}")
                    continue
                
                if poll_name:
                    poll_functions.append(poll_name)
                    print(f"[rust-future-tracing] Mapped future -> poll: {future_name} -> {poll_name} (DIE offset: {poll_offset})")
                else:
                    print(f"[rust-future-tracing] WARNING: Could not build poll function name for future: {future_name}")
            else:
                print(f"[rust-future-tracing] WARNING: No poll function found for future: {future_name}")
        
        # Also handle async functions that were expanded (convert them to function names)
        async_functions = validated_futures.get("async_functions", [])
        for async_info in async_functions:
            async_offset = async_info["offset"]
            async_die = async_info["die"]
            async_name = async_info["name"]
            
            print(f"[rust-future-tracing] Including async function: {async_name} (offset: {async_offset})")
            
            # Build the full async function name
            full_async_name = self._build_poll_function_name(async_die, async_name)
            if full_async_name:
                poll_functions.append(full_async_name)
                print(f"[rust-future-tracing] Added async function: {full_async_name}")
        
        # Remove duplicates while preserving order
        unique_poll_functions = []
        seen = set()
        for func in poll_functions:
            if func not in seen:
                unique_poll_functions.append(func)
                seen.add(func)
        
        print(f"[rust-future-tracing] Step 4 complete. Found {len(unique_poll_functions)} unique poll functions:")
        for i, func in enumerate(unique_poll_functions, 1):
            print(f"  {i}. {func}")
        
        return unique_poll_functions

    def invoke(self, arg, from_tty):
        # === STEP 1: Read poll_map.json and convert interesting poll functions to futures ===
        print("[rust-future-tracing] Step 1: Reading user-selected interesting functions...")
        
        interesting_futures = self._read_interesting_functions_and_convert_to_futures()
        if not interesting_futures:
            print("[rust-future-tracing] No interesting functions found. Please mark functions with 'async_backtrace': true in poll_map.json")
            return
        
        print(f"[rust-future-tracing] Found {len(interesting_futures)} interesting futures:")
        for future in interesting_futures:
            print(f"  - {future}")
        
        # === STEP 3: Perform future expansion ===
        expansion_results = self.perform_future_expansion(interesting_futures)
        
        if not expansion_results:
            print("[rust-future-tracing] Future expansion failed, cannot continue")
            return
        
        # Store expansion results for Step 4
        self.expansion_results = expansion_results
        
        print(f"[rust-future-tracing] Step 3 complete. Expanded to {len(expansion_results.get('expansion_info', {}).get('expanded_offsets', []))} total futures")
        
        # === STEP 4: Convert expanded futures to poll functions ===
        poll_functions_to_instrument = self.convert_expanded_futures_to_poll_functions(expansion_results)
        
        if not poll_functions_to_instrument:
            print("[rust-future-tracing] No poll functions found from expanded futures, cannot continue")
            return
        
        print(f"[rust-future-tracing] Step 4 complete. Ready to instrument {len(poll_functions_to_instrument)} poll functions")
        
        # === STEP 5 & 6: Set up instrumentation using the async backtrace plugin ===
        # This plugin will use the tracer to collect data into async_backtrace_store
        plugin = AsyncBacktracePlugin(poll_functions_to_instrument, expansion_results)
        
        # The original instrumentation logic from gdb-debugger
        # This will set the breakpoints and run the tracers
        global traced_data
        traced_data = defaultdict(list)
        
        instrument_points = plugin.instrument_points()
        for point in instrument_points:
            spec = point["symbol"]
            entry_tracers = point.get("entry_tracers", [])
            exit_tracers = point.get("exit_tracers", [])
            
            # Use EntryBreakpoint which handles both entry and exit tracers correctly
            EntryBreakpoint(spec, entry_tracers, exit_tracers)        
        print("[rust-future-tracing] All steps complete. Instrumentation is active.")
        print("Hint: Use 'continue' or 'run' to start the program, then 'inspect-async' to see results.")

from .runtime_plugins.async_backtrace_plugin import AsyncBacktracePlugin
from .runtime_plugins.async_backtrace_data import async_backtrace_store
from collections import defaultdict


class InspectAsync(gdb.Command):
    """
    Inspects the current state of asynchronous tasks and prints the
    captured asynchronous backtraces.
    This command implements Step 7.
    """
    def __init__(self):
        super().__init__("inspect-async", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        
        backtraces = async_backtrace_store.get_backtraces()
        offset_to_name = async_backtrace_store.get_offset_to_name_map()

        if not backtraces:
            print("[rust-future-tracing] No asynchronous backtrace data collected.")
            print("Hint: Run the 'start-async-debug' command and then 'continue' or 'run' the program.")
            return

        print("=" * 80)
        print(" " * 28 + "Asynchronous Backtraces")
        print("=" * 80)

        for pid, thread_map in backtraces.items():
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

StartAsyncDebugCommand()
InspectAsync()
