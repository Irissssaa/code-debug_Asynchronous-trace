use super::kretprobes::{register_kretprobe, register_kretprobe_with_symbol};
use alloc::sync::Arc;
use super::{KRetProbeArgs, TrapFrame};

#[inline(never)]
fn recursive_fn(i: isize) -> isize {
    if i >= 5 {
        return 100;
    }

    warn!("in recursive_fn({})", i);
    return i + recursive_fn(i + 1);
}

fn test_entry_handler(tf: &mut TrapFrame, _data: usize) -> isize {
    warn!("entering fn, a0 = {}", tf.general.a0);
    0
}

fn test_exit_handler(tf: &mut TrapFrame, _data: usize) -> isize {
    warn!("exiting fn, a0 = {}", tf.general.a0);
    0
}
fn sleep_entry_handler(tf: &mut TrapFrame, _data: usize) -> isize {
    0
}

fn sleep_exit_handler(tf: &mut TrapFrame, _data: usize) -> isize {
    warn!("exiting sleep, a0 = {}", tf.general.a0);
    if tf.general.a0 == 1 {
        warn!("sleeping!");
    } else {
        warn!("woken up!");
    }
    0
}

pub fn run_kretprobes_test() {
    let args = KRetProbeArgs {
        exit_handler: Arc::new(test_exit_handler),
        entry_handler: Some(Arc::new(test_entry_handler)),
        limit: None,
        user_data: 0,
    };
    register_kretprobe(recursive_fn as usize, args);
    recursive_fn(1);
    register_kretprobe_with_symbol(
        "<kernel_hal::common::future::SleepFuture as core::future::future::Future>::poll",
        KRetProbeArgs {
            exit_handler: Arc::new(sleep_exit_handler),
            entry_handler: Some(Arc::new(sleep_entry_handler)),
            limit: None,
            user_data: 0,
        },
    );
}
