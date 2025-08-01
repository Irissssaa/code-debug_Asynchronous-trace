Excellent! With all the pieces in place and `async_dependencies.json` generated, you are ready to test the full asynchronous backtracing functionality.

Here is a step-by-step guide to run a test:

### Step 1: Mark Functions of Interest in `poll_map.json`

First, you need to tell the tool which asynchronous operations you want to trace. You do this by editing the poll_map.json file.

1.  Open the file poll_map.json.
2.  Find the entry for a poll function you are interested in (for example, one related to `reqwest::get`).
3.  In that function's entry, add or set the key `"async_backtrace"` to `true`.

**Example poll_map.json entry:**

```json
{
  "/home/oslab/rust-future-tracing/tests/tokio_test_project/src/main.rs": {
    "fn_name": "reqwest::get::{async_fn#0}<&str>",
    "line_number": 20,
    "is_async": true,
    "async_backtrace": true,  // <--- SET THIS TO TRUE
    "dependencies": [
      "reqwest::async_impl::client::Pending"
    ]
  },
  "...": "..."
}
```

### Step 2: Launch the Debugger

Use the provided Makefile target to launch GDB with the correct environment and test program. This command builds the test project and correctly sets the `PYTHONPATH` for GDB to find the necessary Python modules.

In your terminal, run:

 Excellent! Now that all the pieces are in place, here is a step-by-step guide to test the full async debugging workflow inside GDB.

Since `async_dependencies.json` is already generated, you can proceed directly with the debugging commands.

### Step-by-Step Testing Guide

1.  **Launch GDB with the Test Program**:
    You've already done this correctly. The `make test-gdb` command is the perfect way to start, as it sets up the necessary `PYTHONPATH` to include the virtual environment.

    ```bash
    make test-gdb
    ```

2.  **Initialize DWARF Analysis**:
    Once GDB starts, the first command you need to run is `init-dwarf-analysis`. This builds the DWARF tree in memory, which is essential for all subsequent steps.

    ```gdb
    (gdb) init-dwarf-analysis
    ```
    You should see output indicating that the DWARF tree is being parsed and initialized.

3.  **Set "Interesting" Functions (If Needed)**:
    Before starting the debugger, make sure you have marked at least one function in poll_map.json with `"async_backtrace": true`. For example, to trace the `reqwest::get` future, your `poll_map.json` might contain an entry like this:

    ```json
    {
      ".../tokio_test_project/src/main.rs": {
        "fn_name": "reqwest::get::{async_fn#0}<&str>",
        "async_backtrace": true
      }
    }
    ```
    If you need to modify this file, you can do so now before the next step.

4.  **Start the Async Debugger**:
    Now, run the main command `start-async-debug`. This will execute all the steps we've built:
    *   Read `poll_map.json` (Step 1)
    *   Convert poll functions to futures and get their DIE offsets (Step 2)
    *   Expand dependencies using `async_dependencies.json` (Step 3)
    *   Convert the expanded futures back to poll functions (Step 4)
    *   Set up the `AsyncBacktracePlugin` and `AsyncBacktraceTracer` (Steps 5 & 6)
    *   Set all the necessary breakpoints.

    ```gdb
    (gdb) start-async-debug
    ```
    You will see a lot of output detailing the progress of each step.

5.  **Run the Program**:
    With the instrumentation active, run the program using the `continue` (or `c`) command. The program will run, and the breakpoints we set will trigger the `AsyncBacktraceTracer` to collect data.

    ```gdb
    (gdb) continue
    ```
    The program will run to completion.

6.  **Inspect the Results (Step 7)**:
    This is the final step. Use the `inspect-async` command to view the captured asynchronous backtraces.

    ```gdb
    (gdb) inspect-async
    ```

You should now see a beautifully formatted output showing the asynchronous call stacks for each coroutine that was traced, similar to the structure we designed. This will validate that the entire pipeline is working correctly.
