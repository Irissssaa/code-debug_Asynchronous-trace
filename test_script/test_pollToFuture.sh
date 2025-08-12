#!/bin/bash

# Test script for pollToFuture method
cd /home/oslab/rust-future-tracing

echo "=== Testing pollToFuture Method ==="
echo "Loading tokio test project in GDB..."

# Activate virtual environment and run GDB with proper Python path
source venv/bin/activate

# Start GDB with the tokio test project and run our Python test
gdb -batch \
  -ex "set confirm off" \
  -ex "file tests/tokio_test_project/target/debug/tokio_test_project" \
  -ex "source test_pollToFuture_gdb.py"
import sys
sys.path.insert(0, '/home/oslab/rust-future-tracing/src')

# Initialize DWARF analysis first
from core.init_dwarf_analysis import initDwarfAnalysisCommand
init_cmd = initDwarfAnalysisCommand()
init_cmd.invoke('', False)

# Now test pollToFuture
from core import StartAsyncDebugCommand
cmd = StartAsyncDebugCommand()

print()
print('=== Testing pollToFuture Method ===')

# Test cases
test_cases = [
    'reqwest::get::{async_fn#0}',
    'hyper::client::conn::http1::ready::{async_fn#0}', 
    'h2::client::bind_connection::{async_fn#0}',
    'tokio::time::sleep::{async_fn#0}',
    'static fn reqwest::get::{async_fn#0}<&str>(url: &str)',
]

for i, poll_fn_name in enumerate(test_cases):
    print(f'\\nTest {i+1}: {poll_fn_name}')
    print('-' * 60)
    
    try:
        # Test hierarchy parsing first
        hierarchy = cmd.parse_poll_function_hierarchy(poll_fn_name)
        print(f'  Parsed hierarchy: {hierarchy}')
        
        # Test the full pollToFuture method
        result = cmd.pollToFuture(poll_fn_name)
        print(f'  Result: {result}')
        
    except Exception as e:
        print(f'  ERROR: {e}')
        import traceback
        traceback.print_exc()

print('\\n=== Test Complete ===')
end
quit
"
