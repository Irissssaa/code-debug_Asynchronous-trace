use addr2line::{Context, Location};
use fallible_iterator::FallibleIterator;
use gimli::{EndianSlice, RunTimeEndian};
use core::convert::TryFrom;
use core::fmt;
use alloc::borrow::Cow;

#[inline]
pub fn print(args: fmt::Arguments) {
    kernel_hal::console::console_write_fmt(args);
}

macro_rules! print {
    ($($arg:tt)*) => {
        print(core::format_args!($($arg)*));
    }
}

macro_rules! println {
    () => (print!("\r\n"));
    ($($arg:tt)*) => {
        print(core::format_args!($($arg)*));
        print!("\r\n");
    }
}

fn print_loc(loc: Option<&Location>, llvm: bool) {
    if let Some(ref loc) = loc {
        if let Some(ref file) = loc.file.as_ref() {
            let path = file;
            print!("{}:", path);
        } else {
            print!("??:");
        }
        if llvm {
            print!("{}:{}", loc.line.unwrap_or(0), loc.column.unwrap_or(0));
        } else if let Some(line) = loc.line {
            print!("{}", line);
        } else {
            print!("?");
        }
        println!();
    } else if llvm {
        println!("??:0:0");
    } else {
        println!("??:0");
    }
}

fn print_function(name: Option<&str>, language: Option<gimli::DwLang>, demangle: bool) {
    if let Some(name) = name {
        if demangle {
            print!("{}", addr2line::demangle_auto(Cow::from(name), language));
        } else {
            print!("{}", name);
        }
    } else {
        print!("??");
    }
}

pub fn print_from_addr(probe: usize, ctx: &Context<EndianSlice<RunTimeEndian>>) {
    let demangle = true;
    let llvm = true;
    println!("PC: 0x{:x}", probe);
    let mut frames = ctx.find_frames(u64::try_from(probe).unwrap()).unwrap().enumerate();
    while let Some((i, frame)) = frames.next().unwrap() {
        if i != 0 {
            print!(" (inlined by) ");
        }

        if let Some(func) = frame.function {
            print_function(
                func.raw_name().ok().as_ref().map(AsRef::as_ref),
                func.language,
                demangle,
            );
        }

        print!(" at ");
        print_loc(frame.location.as_ref(), llvm);
    }
}