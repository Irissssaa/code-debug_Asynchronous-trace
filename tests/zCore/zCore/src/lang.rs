// Rust language features implementations

use core::panic::PanicInfo;
use super::backtrace;

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    println!("\n\npanic cpu={}\n{}", kernel_hal::cpu::cpu_id(), info);
    error!("\n\n{info}");
    #[cfg(any(target_arch = "riscv32", target_arch = "riscv64"))]
    backtrace::backtrace();

    if cfg!(feature = "baremetal-test") {
        kernel_hal::cpu::reset();
    } else {
        loop {
            core::hint::spin_loop();
        }
    }
}
