use crate::fs::INodeExt;
use alloc::sync::Arc;
use crate::fs::vfs::FileSystem;
use lock::Mutex;
use alloc::vec::Vec;
use core::str::{from_utf8};
mod parse;
mod address;
mod stacktrace;

pub use stacktrace::print_stacktrace;

static ROOTFS: Mutex<Option<Arc<dyn FileSystem>>> = Mutex::new(None);

pub fn init_debuginfo(rootfs: &Arc<dyn FileSystem>) {
    match rootfs.root_inode().lookup("./zcore") {
        Ok(_) => {
            ROOTFS.lock().replace(rootfs.clone());
            ()
        }
        Err(e) => error!("failed to lookup /zcore: {:?}, debuginfo can't be used", e)
    }
}

pub fn print_trace(probe: Vec<usize>) {
    let inode = match ROOTFS.lock().as_ref().unwrap()
    .root_inode().lookup("./zcore") {
        Ok(inode) => inode,
        Err(e) => {
            error!("failed to lookup /zcore: {:?}, debuginfo can't be used", e);
            return;
        }
    };
    let data = inode.read_as_vec().unwrap();
    parse::parse_elf_and_print(data, probe).unwrap();
}

pub fn init_symtab() {
    let inode = match ROOTFS.lock().as_ref().unwrap()
    .root_inode().lookup("./zcore.sym") {
        Ok(inode) => inode,
        Err(e) => {
            error!("failed to lookup /zcore.sym: {:?}, symbol table can't be used", e);
            return;
        }
    };
    let data = inode.read_as_vec().unwrap();
    let symtab = from_utf8(data.as_slice()).unwrap();
    zircon_object::symbol::init_symbol_table(symtab);
}