from ...core.tracers.base import Tracer
import gdb
import subprocess

class ContextTracer(Tracer):
    """
    A highly specialized tracer that finds the Tokio CONTEXT variable by
    calling an external C program to perform the complex memory parsing.
    """
    def __init__(self):
        super().__init__()

    def start(self, inferior_thread: gdb.Thread):
        try:
            inferior_thread.switch()
            
            # 1. Get the Header pointer from self.ptr.pointer
            header_ptr_val = gdb.parse_and_eval("self.ptr.pointer")
            header_addr = int(header_ptr_val)

            # 2. Get the vtable from the Header struct
            vtable_ptr_val = header_ptr_val.dereference()['vtable']
            
            # 3. Get the scheduler_offset from the VTable struct
            vtable_struct = vtable_ptr_val.dereference()
            scheduler_offset = int(vtable_struct['scheduler_offset'])
            
            # 4. Calculate the address of the scheduler Handle
            scheduler_addr = header_addr + scheduler_offset
            
            # 5. Call the external C program to get the context address
            result = subprocess.run(
                ['./gdb_debugger/get_context', hex(scheduler_addr)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.data = f"Error: get_context helper failed: {result.stderr}"
                return

            context_addr = int(result.stdout.strip(), 16)
            
            # 6. Cast this raw address to a gdb.Value
            context_type = gdb.lookup_type("tokio::runtime::context::Context")
            self.data = gdb.Value(context_addr).cast(context_type.pointer())

        except (gdb.error, gdb.MemoryError) as e:
            self.data = f"Error: {e}"
            print(f"[gdb_debugger] tracer warning: could not trace CONTEXT from helper: {e}")

    def stop(self):
        pass
        
    def __str__(self) -> str:
        return "ContextTracer" 
