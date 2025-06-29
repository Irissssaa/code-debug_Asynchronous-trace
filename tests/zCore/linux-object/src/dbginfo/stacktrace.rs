use core::arch::asm;
use core::mem::size_of;

extern "C" {
    fn stext();
    fn etext();
    fn sstack();
}

/// Returns the current frame pointer or stack base pointer
#[inline(always)]
pub fn fp() -> usize {
    let ptr: usize;
    #[cfg(any(target_arch = "riscv32", target_arch = "riscv64"))]
    unsafe {
        asm!("mv {}, s0", out(reg) ptr);
    }
    ptr
}

/// Returns the current link register.or return address
#[inline(always)]
pub fn lr() -> usize {
    let ptr: usize;
    #[cfg(any(target_arch = "riscv32", target_arch = "riscv64"))]
    unsafe {
        asm!("mv {}, ra", out(reg) ptr);
    }
    ptr
}

pub fn print_stacktrace() {
    #[cfg(any(target_arch = "riscv32", target_arch = "riscv64"))]
    unsafe {
        let mut current_pc = lr();
        let mut current_fp = fp();
        let mut trace_pc = vec!();
        warn!("=== BEGIN zCore stack trace ===");

        while current_pc >= stext as usize
            && current_pc <= etext as usize
            && current_fp as usize != 0
        {

            trace_pc.push(current_pc - size_of::<usize>());
            #[cfg(any(target_arch = "riscv32", target_arch = "riscv64"))]
            {
                current_fp = *(current_fp as *const usize).offset(-2);
                // raw address 0x803ba000 appeared in the backtrace and I don't know why, traced into bootloading phase?
                if current_fp < sstack as usize {
                    break;
                }
                current_pc = *(current_fp as *const usize).offset(-1);
            }
        }
        super::print_trace(trace_pc);
        warn!("=== END zCore stack trace ===");
    }
}