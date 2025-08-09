from ...core.tracers.base import Tracer
import gdb

class TaskListTracer(Tracer):
    """
    A highly specialized tracer that finds the Tokio owned task list by
    navigating from the `self` argument in a poll call, using the
    exact dereferencing path we discovered together.
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
            
            # 5. Cast the address to a Handle pointer
            handle_type = gdb.lookup_type("tokio::runtime::scheduler::multi_thread::handle::Handle")
            handle_val = gdb.Value(scheduler_addr).cast(handle_type.pointer()).dereference()

            # 6. The task list is inside the `shared` and `owned` fields.
            self.data = handle_val['shared']['owned']

        except (gdb.error, gdb.MemoryError) as e:
            self.data = f"Error: {e}"
            print(f"[gdb_debugger] tracer warning: could not trace task list from Handle: {e}")

    def stop(self):
        pass
        
    def __str__(self) -> str:
        return "TaskListTracer" 