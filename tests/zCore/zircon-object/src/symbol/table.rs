use alloc::string::*;
use alloc::vec::*;
use lock::Mutex;
use lazy_static::lazy_static;

pub struct SymbolTable {
    // sorted by address
    pub kernel_symbols: Vec<(String, usize)>,
}

lazy_static! {
    static ref SYMBOL_TABLE: Mutex<Option<SymbolTable>> = Mutex::new(None);
}

impl SymbolTable {
    pub fn new() -> Self {
        Self {
            kernel_symbols: Vec::new(),
        }
    }

    pub fn add_symbol(&mut self, name: String, addr: usize) {
        self.kernel_symbols.push((name, addr));
    }

    /// name to address
    pub fn translate(&self, name: &str) -> Option<usize> {
        for (symbol_name, addr) in self.kernel_symbols.iter() {
            if symbol_name == name {
                return Some(*addr);
            }
        }
        None
    }

    /// binary search, returns symbol name and symbol address
    pub fn find_symbol(&self, addr: usize) -> Option<(&str, usize)> {
        let mut l: usize = 0;
        let mut r = self.kernel_symbols.len();
        while l < r {
            let m = l + (r - l) / 2;
            if self.kernel_symbols[m].1 <= addr {
                l = m + 1;
            } else {
                r = m;
            }
        }
        if l > 0 {
            Some((&self.kernel_symbols[l - 1].0, self.kernel_symbols[l - 1].1))
        } else {
            None
        }
    }

    pub fn init_kernel_symbols(&mut self, kernel_symbols: &str) {
        let lines = kernel_symbols.lines();
        for l in lines.into_iter() {
            let mut words = l.split_whitespace();
            let address = words.next().unwrap();
            let _stype = words.next().unwrap();
            let remaining: Vec<_> = words.collect();
            let name: &str = &remaining.join(" ");
            let addr = usize::from_str_radix(address, 16).unwrap();
            self.add_symbol(name.to_string(), addr);
        }
    }

    /// should be called only once with the symbol table string
    pub fn init(symtab: &str) {
        info!("Symbol Table loading...");
        let mut table = Self::new();
        table.init_kernel_symbols(symtab);
        SYMBOL_TABLE.lock().replace(table);
        info!("Symbol Table loaded!");
    }
}

/// Initialize with a string representing the symbol table.
pub fn init_symbol_table(symtab: &str) {
    SymbolTable::init(symtab);
}

pub fn symbol_to_addr(name: &str) -> Option<usize> {
    let addr = SYMBOL_TABLE.lock().as_ref().unwrap().translate(name);
    addr
}

pub fn symbol_table_with<T>(f: impl FnOnce(&SymbolTable) -> T) -> T {
    let table = SYMBOL_TABLE.lock();
    let symbols = table.as_ref().unwrap();
    f(symbols)
}
