/*
 * Generic Linker Script for ARM Cortex-M targets
 * FINAL CORRECTED VERSION - Removed the unnecessary PROVIDE for __pre_init.
 */

/* Specify the memory areas */
MEMORY
{
  /* Flash memory (ROM) */
  FLASH : ORIGIN = 0x00000000, LENGTH = 512K
  /* RAM */
  RAM   : ORIGIN = 0x20000000, LENGTH = 128K
}

/* Define entry point */
ENTRY(Reset);

/* * We removed the problematic 'PROVIDE(__pre_init = DefaultHandler);' line.
 * The cortex-m-rt crate will provide its own weak default.
 */

/* Define sections */
SECTIONS
{
    .vector_table :
    {
        . = ALIGN(4);
        KEEP(*(.vector_table)) /* Vector table */
    } > FLASH

    .text :
    {
        . = ALIGN(4);
        *(.text*)       /* .text sections (code) */
        . = ALIGN(4);
    } > FLASH

    .rodata :
    {
        . = ALIGN(4);
        *(.rodata*)     /* .rodata sections (constants) */
        . = ALIGN(4);
    } > FLASH

    __sidata = .;

    .data : AT (__sidata)
    {
        __sdata = .;
        *(.data*)      /* .data sections */
        __edata = .;
    } > RAM

    .bss :
    {
        __sbss = .;
        *(.bss*)       /* .bss sections */
        *(COMMON)
        __ebss = .;
    } > RAM

    /* Set stack top to end of RAM */
    __estack = ORIGIN(RAM) + LENGTH(RAM);

    /DISCARD/ :
    {
        *(.ARM.exidx*)
    }
}
