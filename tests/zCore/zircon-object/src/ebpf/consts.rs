// see Linux kernel source /include/uapi/linux/bpf.h

// eBPF syscall commands
use numeric_enum_macro::numeric_enum;

numeric_enum! {
    #[repr(i32)]

    #[derive(Debug, PartialEq, PartialOrd, Ord, Eq, Hash)]
    #[allow(non_camel_case_types)]
    pub enum BpfCommand {
        #[allow(non_camel_case_types)]
        BPF_MAP_CREATE = 0,
        BPF_MAP_LOOKUP_ELEM = 1,
        BPF_MAP_UPDATE_ELEM = 2,
        BPF_MAP_DELETE_ELEM = 3,
        BPF_MAP_GET_NEXT_KEY = 4,
        BPF_PROG_LOAD = 5,
        BPF_PROG_ATTACH = 8,
        BPF_PROG_DETACH = 9,
        BPF_PROG_LOAD_EX = 1000,
    }
}


// eBPF map types
pub const BPF_MAP_TYPE_UNSPEC: u32 = 0;
pub const BPF_MAP_TYPE_HASH: u32 = 1;
pub const BPF_MAP_TYPE_ARRAY: u32 = 2;
pub const BPF_MAP_TYPE_PROG_ARRAY: u32 = 3;

// eBPF LLVM relocations
// see https://www.kernel.org/doc/html/latest/bpf/llvm_reloc.html
pub const R_BPF_NONE: u32 = 0;
pub const R_BPF_64_64: u32 = 1;
pub const R_BPF_64_ABS64: u32 = 2;
pub const R_BPF_64_ABS32: u32 = 3;
pub const R_BPF_64_NODYLD32: u32 = 4;
pub const R_BPF_64_32: u32 = 10;

pub const BPF_ANY: u64 = 0;
pub const BPF_NOEXIST: u64 = 1;
pub const BPF_EXIST: u64 = 2;
pub const BPF_F_LOCK: u64 = 4;

