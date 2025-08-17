#![no_std]
#![no_main]

use embassy_cortex_m::bind_interrupts;
use embassy_cortex_m::executor::InterruptExecutor;
use embassy_executor::Spawner;
use embassy_time::{Duration, Timer};
use static_cell::StaticCell;
use defmt::{info, println};
use panic_probe as _;
use defmt_rtt as _;
use cortex_m_rt::entry;
use cortex_m_rt::pre_init;

bind_interrupts!(struct Irqs {
    // 使用一个通用的软件中断
    SWI0_EGU0 => InterruptExecutor;
});

#[pre_init]
unsafe fn pre_init() {}

#[embassy_executor::task]
async fn main_task(_spawner: Spawner) {
    println!("-- Generic Embassy Test Program Started --");
    
    // 为了最终测试，我们简化为单个任务循环
    let mut count = 0;
    loop {
        info!("Hello from the generic main task! Count: {}", count);
        count += 1;
        Timer::after(Duration::from_secs(1)).await;
    }
}

#[entry]
fn main() -> ! {
    // 这里不再需要任何芯片相关的 init 函数
    static EXECUTOR: StaticCell<InterruptExecutor> = StaticCell::new();
    let executor = EXECUTOR.init(InterruptExecutor::new());
    executor.run(|spawner| {
        spawner.spawn(main_task(spawner.clone())).unwrap();
    })
}
