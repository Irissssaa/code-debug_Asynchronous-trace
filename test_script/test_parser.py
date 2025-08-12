#!/usr/bin/env python3

import re

def parse_poll_function_hierarchy(poll_fn_name):
    """
    Parse a poll function name into hierarchical components.
    
    Args:
        poll_fn_name (str): Poll function name like "reqwest::get::{async_fn#0}"
        
    Returns:
        list: Hierarchical components, e.g., ["reqwest", "get", "{async_fn#0}"]
    """
    
    # Remove function signature parts (parameters and return type)
    # First remove the "static fn " prefix if present
    cleaned_name = re.sub(r'^static fn\s+', '', poll_fn_name)
    
    # Find the function name part before the first opening parenthesis or angle bracket
    # This handles cases like "reqwest::get::{async_fn#0}<&str>(...)"
    match = re.match(r'([^<(]+)', cleaned_name)
    if not match:
        return []
    
    function_path = match.group(1).strip()
    
    # Split by "::" to get namespace hierarchy
    components = function_path.split('::')
    
    # Filter out empty components
    components = [comp.strip() for comp in components if comp.strip()]
    
    return components

# Test cases from poll_map.json
test_cases = [
    'static fn reqwest::get::{async_fn#0}<&str>(*mut core::task::wake::Context)',
    'static fn hyper::client::conn::http1::{impl#1}::ready::{async_fn#0}<reqwest::async_impl::body::Body>(*mut core::task::wake::Context)',
    'static fn h2::client::bind_connection::{async_fn#0}<hyper::common::io::compat::Compat<reqwest::connect::sealed::Conn>>(*mut core::task::wake::Context)',
    'hyper_util::client::legacy::client::{impl#1}::try_send_request::{async_fn#0}::{closure_env#1}',
    'futures_channel::mpsc::BoundedSenderInner::poll_ready'
]

print("Testing poll function hierarchy parsing:")
print("=" * 80)

for i, test_case in enumerate(test_cases, 1):
    result = parse_poll_function_hierarchy(test_case)
    print(f"Test {i}:")
    print(f"Input:  {test_case}")
    print(f"Result: {result}")
    print("-" * 80)
