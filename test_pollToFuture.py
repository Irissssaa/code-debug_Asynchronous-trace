#!/usr/bin/env python3
"""
Test script for pollToFuture method.
This script should be run inside GDB with the tokio_test_project loaded.
"""

def test_pollToFuture():
    """Test the pollToFuture method with sample poll function names."""
    
    # Import the command class
    import sys
    sys.path.insert(0, '/home/oslab/rust-future-tracing/src')
    
    from core import StartAsyncDebugCommand
    
    # Create an instance of the command
    cmd = StartAsyncDebugCommand()
    
    # Test cases from poll_map.json
    test_cases = [
        "reqwest::get::{async_fn#0}",
        "hyper::client::conn::http1::ready::{async_fn#0}", 
        "h2::client::bind_connection::{async_fn#0}",
        "tokio::time::sleep::{async_fn#0}",
        "static fn reqwest::get::{async_fn#0}<&str>(url: &str)",
    ]
    
    print("=== Testing pollToFuture Method ===")
    print("Make sure you have run 'init-dwarf-analysis' first!\n")
    
    for i, poll_fn_name in enumerate(test_cases):
        print(f"Test {i+1}: {poll_fn_name}")
        print("-" * 60)
        
        try:
            # Test hierarchy parsing first
            hierarchy = cmd.parse_poll_function_hierarchy(poll_fn_name)
            print(f"  Parsed hierarchy: {hierarchy}")
            
            # Test the full pollToFuture method
            result = cmd.pollToFuture(poll_fn_name)
            print(f"  Result: {result}")
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        print()

if __name__ == "__main__":
    test_pollToFuture()
