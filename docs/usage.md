# Async Debugger Usage Guide

> This is the current end-to-end workflow. Earlier notes in `guide.md` and `async_backtrace.md` are archived and no longer reflect the toolchain.

## Prerequisites

- Rust toolchain with `cargo` (the bundled `tests/tokio_test_project` compiles in debug mode).
- A `.cargo/config.toml` in your workspace matching the sample at `tests/tokio_test_project/.cargo/config.toml`. Copy or adapt the `[build]` and `[target.*]` settings there so `cargo` emits the expected LLVM bitcode and DWARF info for analysis.
- LLVM tools that match your `rustc` build. Run `rustc --version --verbose` and copy the reported `LLVM version`. Install that version of `llvm`/`llvm-tools` (e.g., on Ubuntu `sudo apt-get install llvm-20 llvm-20-tools`) so the `opt` binary can generate call graphs from the emitted IR.
- Python 3.10+ virtualenv with the dependencies in `src/requirements.txt` (run `make venv` once from the repo root).
- GDB with Python support (Ubuntu `sudo apt install gdb` is sufficient).
- From the repo root, activate the virtualenv before launching the workflow: `source venv/bin/activate`.

## Step-by-step workflow

### Step 1 – Build and launch via `make`

Run the integrated recipe from the project root:

```
make test-tokio_test_project
```

This target does the following:

1. Builds `tests/tokio_test_project` (debug profile) so that the binary at `tests/tokio_test_project/target/debug/tokio_test_project` is up to date.
2. Regenerates `results/tokio_test_project.callgraph.dot` and `results/async_dependencies.json`.
3. Starts `gdb-multiarch` with `src/main.py` preloaded and runs the freshly built binary.

Leave the GDB session open for the remaining steps. If you only need to rerun GDB without rebuilding, the fallback target `make test-tokio_test_project-no-recompile` skips the compilation and artifact refresh.

### Step 2 – Discover poll functions

Inside the GDB prompt, locate all futures that implement `poll`:

```
(gdb) find-poll-fn
```

The command stores a map at `results/poll_map.json`. Open this file in your editor and flip the `"async_backtrace"` flag to `true` for every poll function you want to instrument (typically the leaf futures you care about). Leave the flag `false` for noisy or irrelevant entries. Save the file before continuing.

> Tip: If you rerun `find-poll-fn`, it overwrites the JSON. Keep a copy (e.g., `results/poll_map.custom.json`) if you maintain curated selections across sessions.

### Step 3 – Load DWARF metadata

Still inside GDB, initialize the DWARF tree so the debugger can resolve future hierarchies:

```
(gdb) init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
```

Replace the path if you are debugging a different binary. A successful run reports how many compilation units were indexed and exposes them as `gdb.dwarf_tree` and `gdb.dwarf_info` for ad-hoc inspection.

### Step 4 – Start the async analysis

Kick off the tracing pipeline so the selected futures are instrumented:

```
(gdb) start-async-analysis
```

> In the current repository the command name is `start-async-debug`. If your setup exposes `start-async-analysis` as an alias, either form is equivalent.

After the command confirms breakpoints, run or continue the program (`run`/`continue`). While it executes you can:

- Inspect live async stacks with `inspect-async`.
- Dump the collected event log with `dump-async-data` (writes to `results/async_backtrace.json`).
- Exit the session with `quit` when finished.

## Additional notes

- All generated artifacts (call graph, async dependencies, poll map, traces) are kept under `results/` so they survive across runs.
- The instrumentation depth is controlled by `ENABLE_SYNC_DESCENDANTS`, `ENABLE_ASYNC_DESCENDANTS`, and `SYNC_DESCENDANT_DEPTH` in `src/core/config.py`.
- If you update the Rust sources, rerun `make test-tokio_test_project` to refresh the LLVM bitcode and regenerated files before returning to GDB.
