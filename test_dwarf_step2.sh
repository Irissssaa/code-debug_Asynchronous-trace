#!/bin/bash
cd /home/oslab/rust-future-tracing
PYTHONPATH="venv/lib/python3.12/site-packages:$PYTHONPATH" gdb -q tests/tokio_test_project/target/debug/tokio_test_project << 'EOF'
source src/main.py
init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
python
from core import StartAsyncDebugCommand
cmd = StartAsyncDebugCommand()
cmd.debug_print_compilation_unit(0, 2)
end
quit
EOF
