use alloc::vec::Vec;
use xmas_elf::{ElfFile};
use addr2line::{Context};
use alloc::borrow;
use gimli;
use super::address::print_from_addr;

pub fn parse_elf_and_print(data: Vec<u8>, probes: Vec<usize>) -> Result<(), gimli::Error> {
    let elf = ElfFile::new(&data).unwrap();
    let load_section = |id: gimli::SectionId| -> Result<borrow::Cow<[u8]>, gimli::Error> {
        match elf.find_section_by_name(id.name()) {
            Some(ref section) => Ok(
                section.raw_data(&elf).into()
            ),
            None => Ok(borrow::Cow::Borrowed(&[][..])),
        }
    };
    let dwarf_cow = gimli::Dwarf::load(load_section)?;
    // TODO: hardcode?
    let endian = gimli::RunTimeEndian::Little;
    // Borrow a `Cow<[u8]>` to create an `EndianSlice`.
    let borrow_section: &dyn for<'a> Fn(
        &'a borrow::Cow<[u8]>,
    ) -> gimli::EndianSlice<'a, gimli::RunTimeEndian> =
        &|section| gimli::EndianSlice::new(&*section, endian);

    // Create `EndianSlice`s for all of the sections.
    let dwarf = dwarf_cow.borrow(&borrow_section);

    let ctx = Context::from_dwarf(dwarf).unwrap();
    for probe in probes {
        print_from_addr(probe, &ctx);
    }
    Ok(())
}