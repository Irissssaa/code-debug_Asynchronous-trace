from ...core.tracers.base import Tracer
import gdb
import struct

class TokioTaskIDTracer(Tracer):
    """
    A highly specialized tracer that finds a Tokio task ID from within the
    poll function by navigating the vtable to find the ID's offset.
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
            header_struct = header_ptr_val.dereference()
            vtable_ptr_val = header_struct['vtable']
            
            # 3. Get the id_offset from the VTable struct
            vtable_struct = vtable_ptr_val.dereference()
            id_offset = int(vtable_struct['id_offset'])
            
            # 4. Calculate the final address of the ID
            id_address = header_addr + id_offset
            
            # 5. Read the 8-byte u64 from that address
            memory = gdb.selected_inferior().read_memory(id_address, 8)
            self.data = struct.unpack('<Q', memory)[0]

        except (gdb.error, gdb.MemoryError) as e:
            self.data = f"Error: {e}"
            print(f"[gdb_debugger] tracer warning: could not read task ID from vtable: {e}")

    def stop(self):
        pass
        
    def __str__(self) -> str:
        return "TokioTaskIDTracer" 
