use kernel_hal::mem::{virt_to_phys, phys_to_virt, pmem_copy};
use kernel_hal::KernelHandler;
use lock::Mutex;
use lazy_static::*;

lazy_static! {
    static ref KHANDLER: Mutex<Option<&'static dyn KernelHandler>> = Mutex::new(None);
}

pub const PAGE_SIZE: usize = kernel_hal::PAGE_SIZE;

/// optional function to initialize anything needed
pub fn init_osutils(handler: &'static dyn KernelHandler) {
    KHANDLER.lock().replace(handler);
}

/// Allocate a page of memory, return virtual address
/// The page need to be readable, writable and executable
pub fn alloc_page() -> usize {
    let pa = KHANDLER.lock().unwrap().frame_alloc().unwrap();
    let va = phys_to_virt(pa);
    va
}

/// Deallocate a page of memory from virtual address
pub fn dealloc_page(va: usize) {
    let pa = virt_to_phys(va);
    KHANDLER.lock().unwrap().frame_dealloc(pa);
}

/// Copy memory from src to dst, dst is in user space and src is in kernel space
pub fn byte_copy(dst_addr: usize, src_addr: usize, len: usize) {
    pmem_copy(virt_to_phys(dst_addr),
                virt_to_phys(src_addr),
                len);
}

use crate::symbol::symbol_to_addr as _symbol_to_addr;
/// Convert symbol to address for kprobe registering, not required
pub fn symbol_to_addr(symbol: &str) -> Option<usize> {
    _symbol_to_addr(symbol)
}