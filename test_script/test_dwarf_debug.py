#!/usr/bin/env python3
# Test script to explore DWARF tree structure
# This should be run inside GDB: python exec(open('test_dwarf_debug.py').read())

# Load the core module
import sys
import os

# Add the source directory to path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

try:
    from core.init_dwarf_analysis import initDwarfAnalysisCommand, get_dwarf_tree
    from core import StartAsyncDebugCommand
    
    print("=== Testing DWARF Tree Structure ===")
    
    # Initialize DWARF analysis if not already done
    tree = get_dwarf_tree()
    if not tree:
        print("DWARF tree not found. Please run init-dwarf-analysis first.")
        print("Example: init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project")
    else:
        print(f"DWARF tree found with {len(tree.top_dies)} compilation units")
        
        # Create command instance and test debug print
        cmd = StartAsyncDebugCommand()
        
        # Print first compilation unit structure
        print("\n=== First compilation unit ===")
        cmd.debug_print_compilation_unit(0, 2)
        
        # If there are more CUs, try to find an interesting one
        if len(tree.top_dies) > 5:
            print(f"\n=== Compilation unit 5 (out of {len(tree.top_dies)}) ===")
            cmd.debug_print_compilation_unit(5, 2)
        
        # Look for reqwest-related CUs if they exist
        found_reqwest = False
        for i, cu_die in enumerate(tree.top_dies):
            from core.dwarf.dwarfutil import safe_DIE_name
            cu_name = safe_DIE_name(cu_die, "")
            if "reqwest" in cu_name.lower():
                print(f"\n=== Found reqwest-related CU at index {i}: {cu_name} ===")
                cmd.debug_print_compilation_unit(i, 3)
                found_reqwest = True
                break
        
        if not found_reqwest:
            print("\nNo reqwest-related compilation units found")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
