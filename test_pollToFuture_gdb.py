#!/usr/bin/env python3
"""
GDB Python script to test pollToFuture method.
Run with: gdb -batch -ex "source test_pollToFuture_gdb.py" tests/tokio_test_project/target/debug/tokio_test_project
"""
import sys
import os

# Set up Python path to include our virtual environment and source
venv_path = '/home/oslab/rust-future-tracing/venv/lib/python3.12/site-packages'
src_path = '/home/oslab/rust-future-tracing/src'

if venv_path not in sys.path:
    sys.path.insert(0, venv_path)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    # Initialize DWARF analysis first with the executable path
    from core.init_dwarf_analysis import initDwarfAnalysisCommand
    init_cmd = initDwarfAnalysisCommand()
    init_cmd.invoke('tests/tokio_test_project/target/debug/tokio_test_project', False)
    
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
        print(f'\nTest {i+1}: {poll_fn_name}')
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
    
    print('\n=== Test Complete ===')

except Exception as e:
    print(f'Failed to run test: {e}')
    import traceback
    traceback.print_exc()
