#!/bin/bash

# Test script for pollToFuture method with correct generic names
cd /home/oslab/rust-future-tracing

echo "=== Testing pollToFuture Method with Correct Generic Names ==="
echo "Loading tokio test project in GDB..."

# Activate virtual environment and run GDB with proper Python path
source venv/bin/activate

# Start GDB with the tokio test project and run our Python test
gdb -batch \
  -ex "set confirm off" \
  -ex "file tests/tokio_test_project/target/debug/tokio_test_project" \
  -ex "source test_pollToFuture_with_generics.py"
