#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_time::{Duration, Timer};
use defmt::{info, println};
use panic_probe as _;

use defmt_rtt as _;

// 我们回归到使用这个最简单直接的宏
#[embassy_executor::main]
async fn main(spawner: Spawner) {
    // 初始化 nrf 板级支持
    let _p = embassy_nrf::init(Default::default());
    println!("-- Embassy Test Program Started --");
    
    // 启动并发任务
    spawner.spawn(task_one()).unwrap();
    spawner.spawn(task_two()).unwrap();
    
    let mut count = 0;
    loop {
        info!("In main loop, count: {}", count);
        count += 1;
        Timer::after(Duration::from_secs(5)).await;
    }
}

#[embassy_executor::task]
async fn task_one() {
    loop {
        info!("Hello from Task ONE!");
        Timer::after(Duration::from_secs(1)).await;
    }
}

#[embassy_executor::task]
async fn task_two() {
    loop {
        info!("Hi from Task TWO!");
        Timer::after(Duration::from_millis(2500)).await;
    }
}
