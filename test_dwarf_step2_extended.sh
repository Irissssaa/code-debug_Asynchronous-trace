#!/bin/bash
cd /home/oslab/rust-future-tracing
PYTHONPATH="venv/lib/python3.12/site-packages:$PYTHONPATH" gdb -q tests/tokio_test_project/target/debug/tokio_test_project << 'EOF'
source src/main.py
init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
python
from core import StartAsyncDebugCommand
from core.init_dwarf_analysis import get_dwarf_tree
from core.dwarf.dwarfutil import safe_DIE_name

cmd = StartAsyncDebugCommand()
tree = get_dwarf_tree()

print(f"Total CUs: {len(tree.top_dies)}")

# Look for interesting CUs
for i, cu_die in enumerate(tree.top_dies):
    cu_name = safe_DIE_name(cu_die, "")
    if "reqwest" in cu_name.lower() or "tokio" in cu_name.lower():
        print(f"Found interesting CU {i}: {cu_name}")
        if i < 10:  # Only examine first few
            cmd.debug_print_compilation_unit(i, 2)
            break

# Also check a few random CUs in the middle range
middle_cu = len(tree.top_dies) // 2
print(f"\n=== Middle CU {middle_cu} ===")
cmd.debug_print_compilation_unit(middle_cu, 2)
end
quit
EOF
