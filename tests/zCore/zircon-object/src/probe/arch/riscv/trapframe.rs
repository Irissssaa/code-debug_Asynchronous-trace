pub use trapframe::TrapFrame as TrapFrame;
use core::slice::{from_raw_parts, from_raw_parts_mut};

pub fn get_trapframe_pc(tf: &TrapFrame) -> usize {
    tf.sepc
}

pub fn set_trapframe_pc(tf: &mut TrapFrame, pc: usize) {
    tf.sepc = pc;
}

pub fn get_trapframe_ra(tf: &TrapFrame) -> usize {
    tf.general.ra
}

pub fn set_trapframe_ra(tf: &mut TrapFrame, ra: usize) {
    tf.general.ra = ra;
}

pub fn get_reg(tf: &TrapFrame, reg: u32) -> usize {
    let regs = unsafe { from_raw_parts(&tf.general.zero as *const usize, 32) };
    let index = reg as usize;
    if index != 0 {
        regs[index]
    } else {
        0
    }
}

pub fn set_reg(tf: &mut TrapFrame, reg: u32, val: usize) {
    let regs = unsafe { from_raw_parts_mut(&mut tf.general.zero as *mut usize, 32) };
    let index = reg as usize;
    if index != 0 {
        regs[index] = val;
    }
}
