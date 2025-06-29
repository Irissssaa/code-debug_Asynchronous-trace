// Print the backtrace starting from the caller
pub fn backtrace() {
    linux_object::dbginfo::print_stacktrace();
}