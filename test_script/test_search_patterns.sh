#!/bin/bash
cd /home/oslab/rust-future-tracing
PYTHONPATH="venv/lib/python3.12/site-packages:$PYTHONPATH" gdb -q tests/tokio_test_project/target/debug/tokio_test_project << 'EOF'
source src/main.py
init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
python
from core.init_dwarf_analysis import get_dwarf_tree
from core.dwarf.tree import load_children
from core.dwarf.dwarfutil import safe_DIE_name

tree = get_dwarf_tree()

def search_for_async_patterns(cu_index, max_search=20):
    """Search for async function patterns in a compilation unit"""
    if cu_index >= len(tree.top_dies):
        return
    
    cu_die = tree.top_dies[cu_index]
    
    def search_die_recursive(die, depth=0, max_depth=4):
        if depth > max_depth:
            return
        
        die_name = safe_DIE_name(die, "")
        tag = die.tag if hasattr(die, 'tag') else ""
        
        # Look for interesting patterns
        if ("async_fn#0" in die_name or 
            "async_fn_env#0" in die_name or 
            "get" == die_name or
            "reqwest" in die_name):
            indent = "  " * depth
            print(f"{indent}MATCH: {tag}: {die_name}")
            
            # If this is a namespace, look at siblings
            if die.has_children:
                load_children(die, True)
                for child in die._children[:5]:  # Limit output
                    child_name = safe_DIE_name(child, "")
                    child_tag = child.tag if hasattr(child, 'tag') else ""
                    print(f"{indent}  -> {child_tag}: {child_name}")
        
        # Continue searching children
        if die.has_children and depth < max_depth:
            load_children(die, True)
            for child in die._children[:max_search]:
                search_die_recursive(child, depth + 1, max_depth)
    
    print(f"=== Searching CU {cu_index} for async patterns ===")
    search_die_recursive(cu_die)

# Search several reqwest CUs
for cu_idx in [238, 239, 240]:
    search_for_async_patterns(cu_idx, 10)
    print()

end
quit
EOF
