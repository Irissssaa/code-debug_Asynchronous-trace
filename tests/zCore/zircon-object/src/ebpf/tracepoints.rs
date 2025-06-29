use alloc::collections::BTreeMap;
use alloc::sync::Arc;
use alloc::vec::Vec;
use lazy_static::lazy_static;
use trapframe::TrapFrame;
use crate::symbol::symbol_to_addr;


use lock::Mutex;

use crate::{probe::{register_kprobe, register_kretprobe, KProbeArgs, KRetProbeArgs}, error};
use super::{BpfObject::*, *, retcode::BpfErrorCode::{*, self}, retcode::*};

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct KprobeAttachAttr {
    pub target: *const u8,
    pub str_len: u32,
    pub prog_fd: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum TracepointType {
    KProbe,
    KRetProbeEntry,
    KRetProbeExit,
}

use TracepointType::*;

// Current design is very simple and this is only intended for kprobe/kretprobe
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Tracepoint {
    pub tp_type: TracepointType,
    pub token: usize,
}

impl Tracepoint {
    pub fn new(tp_type: TracepointType, token: usize) -> Self {
        Self { tp_type, token }
    }
}

lazy_static! {
    static ref ATTACHED_PROGS: Mutex<BTreeMap<Tracepoint, Vec<Arc<BpfProgram>>>> =
        Mutex::new(BTreeMap::new());
}

fn run_attached_programs(tracepoint: &Tracepoint, ctx: *const u8) {
    let map = ATTACHED_PROGS.lock();
    let programs = map.get(tracepoint).unwrap();
    for program in programs {
        let _result = program.run(ctx);
        // error!("run result: {}", result);
    }
}

#[repr(C)]
struct KProbeBPFContext {
    ptype: usize,
    paddr: usize,
    tf: TrapFrame,
}

impl KProbeBPFContext {
    pub fn new(tf: &TrapFrame, probed_addr: usize, t: usize) -> Self {
        KProbeBPFContext {
            ptype: t,
            paddr: probed_addr,
            tf: tf.clone()
        }
    }

    pub fn as_ptr(&self) -> *const u8 {
        unsafe { core::mem::transmute(self) }
    }
}

fn kprobe_handler(tf: &mut TrapFrame, probed_addr: usize) -> isize {
    let tracepoint = Tracepoint::new(KProbe, probed_addr);
    let ctx = KProbeBPFContext::new(tf, probed_addr, 0);
    warn!("run attached progs!");
    let obj = BPF_OBJECTS.lock();
    let fd = 1879048193 as u32;
    drop(obj);
    run_attached_programs(&tracepoint, ctx.as_ptr());
    warn!("run attached progs exit!");

    0
}

fn kretprobe_entry_handler(tf: &mut TrapFrame, probed_addr: usize) -> isize {
    let tracepoint = Tracepoint::new(KRetProbeEntry, probed_addr);
    let ctx = KProbeBPFContext::new(tf, probed_addr, 1);
    run_attached_programs(&tracepoint, ctx.as_ptr());
    0
}

fn kretprobe_exit_handler(tf: &mut TrapFrame, probed_addr: usize) -> isize {
    let tracepoint = Tracepoint::new(KRetProbeExit, probed_addr);
    let ctx = KProbeBPFContext::new(tf, probed_addr, 2);
    run_attached_programs(&tracepoint, ctx.as_ptr());
    0
}

fn resolve_symbol(symbol: &str) -> Option<usize> {
    symbol_to_addr(symbol)
}

fn parse_tracepoint<'a>(target: &'a str) -> Result<(TracepointType, &'a str), BpfErrorCode> {
    let pos = target.find('$').ok_or(EINVAL)?;
    let type_str = &target[0..pos];
    let fn_name = &target[(pos + 1)..];

    // determine tracepoint type
    let tp_type: TracepointType;
    if type_str.eq_ignore_ascii_case("kprobe") {
        tp_type = KProbe;
    } else if type_str.eq_ignore_ascii_case("kretprobe@entry") {
        tp_type = KRetProbeEntry;
    } else if type_str.eq_ignore_ascii_case("kretprobe@exit") {
        tp_type = KRetProbeExit;
    } else {
        return Err(EINVAL);
    }
    Ok((tp_type, fn_name))
}

pub fn bpf_program_attach(target: &str, prog_fd: u32) -> BpfResult {
    // check program fd

    warn!("bpf prog attach target: {} \n fd:{}\n", target, prog_fd);

    let program = {
        let objs = BPF_OBJECTS.lock();
        
        match objs.get(&prog_fd) {
            Some(bpf_obj) => {
                let shared_program = bpf_obj.is_program().unwrap();
                trace!("found prog:!");
                Ok(shared_program.clone())
            },
            _ => Err(ENOENT),
        }
    }?;
    warn!("prog found!");
    let (tp_type, fn_name) = parse_tracepoint(target)?;
    warn!("tracepoint parsed: type={:?} fn={}", tp_type, fn_name);
    let addr = resolve_symbol(fn_name).ok_or(ENOENT)?;
    warn!("trace point symbol resolved, symbol:{} addr: {:x}", fn_name, addr);

    let tracepoint = Tracepoint::new(tp_type, addr);

    let mut map = ATTACHED_PROGS.lock();
    if let Some(programs) = map.get_mut(&tracepoint) {
        for other_prog in programs.iter() {
            if Arc::ptr_eq(&program, other_prog) {
                return Err(EAGAIN);
            }
        }
        programs.push(program);
    } else {
        match tp_type {
            KProbe => {
                let args = KProbeArgs {
                    pre_handler: Arc::new(kprobe_handler),
                    post_handler: None,
                    user_data: addr,
                };
                let _ = register_kprobe(addr, args).ok_or(EINVAL)?;
                warn!("kprobe registered at addr: {:x}", addr);
                map.insert(tracepoint, vec![program]);
            }
            KRetProbeEntry | KRetProbeExit => {
                let args = KRetProbeArgs {
                    exit_handler: Arc::new(kretprobe_exit_handler),
                    entry_handler: Some(Arc::new(kretprobe_entry_handler)),
                    limit: None,
                    user_data: addr,
                };
                let _ = register_kretprobe(addr, args).ok_or(EINVAL)?;

                let dual_tp: Tracepoint;
                if tp_type == KRetProbeEntry {
                    dual_tp = Tracepoint::new(KRetProbeExit, addr);
                } else {
                    dual_tp = Tracepoint::new(KRetProbeEntry, addr);
                }
                map.insert(tracepoint, vec![program]);
                map.insert(dual_tp, vec![]);
            }
        }
    }
    warn!("OK");
    Ok(0)
}
