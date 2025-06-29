import argparse
import subprocess
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dump symbol table")
    parser.add_argument("kernel", help="kernel file path")
    parser.add_argument("arch", help="e.g. riscv64")
    parser.add_argument("path", help="dir of the symbol table")
    args = parser.parse_args()
    print(args)
    
    # TODO: no adhoc
    CMD_NM = args.arch + "-linux-musl-" + "nm"
    CMD_OBJDUMP = args.arch  + "-linux-musl-" + "objdump"
    file = args.kernel
    sym_path = os.path.join(args.path, "kernel.sym")
    obj_path = os.path.join(args.path, "kernel.obj")
    tmp_path = os.path.join(args.path, "kernel.tmp")
    
    if not os.path.exists(args.path):
        os.makedirs(args.path)

    symbols = subprocess.check_output([
        CMD_NM, '-C', '-n',
        file])
    with open(sym_path, 'wb') as f:
        f.write(symbols)
    
    dump = subprocess.check_output([
        CMD_OBJDUMP, '-D', '-j', '.text', '-F',
        file])
    with open(obj_path, 'wb') as f:
        f.write(dump)
    '''
    symbol_table_addr, symbol_table_size_addr, sdata = None, None, None
    for line in dump.splitlines():
        line = line.decode().split()
        for word in line:
            if word == '<zcore_symbol_table_size>':
                symbol_table_size_addr = int(line[-1][0:-1], 16)
            if word == '<zcore_symbol_table>':
                symbol_table_addr = int(line[-1][0:-1], 16)
            if word == '<sdata>':
                sdata = int(line[-1][0:-1], 16)
    
    if symbol_table_addr is None:
        # happens when these two coincide
        symbol_table_addr = sdata
        
    print("symbol_table_addr: ", str(hex(symbol_table_addr)))
    print("symbol_table_size_addr: ", str(hex(symbol_table_size_addr)))
    
    size = subprocess.check_output([
        'stat', '-c%s', sym_path])
    size = int(size)
    
    do = subprocess.check_output([
        'dd', 'bs=4096', 'count=' + str(size),
        'if=' + sym_path, 'of=' + file, 'seek=' + str(symbol_table_addr),
        'conv=notrunc', 'iflag=count_bytes', 'oflag=seek_bytes'])
    
    print("symbol table size:", size)
    open(tmp_path, 'wb').write(
        size.to_bytes(8, 'little')
    )
    fsize = subprocess.check_output([
        'stat', '-c%s', tmp_path])
    fsize = int(fsize)
    subprocess.check_output([
        'dd', 'bs=1', 'count=' + str(fsize),
        'if=' + tmp_path, 'of=' + file, 'seek=' + str(symbol_table_size_addr),
        'conv=notrunc'])
    '''
    print("Done dumping symbol table to " + sym_path)
