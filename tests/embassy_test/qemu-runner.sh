#!/bin/sh
set -eu

# 这个脚本的第一个参数 ($1)，就是 Cargo 传递过来的、编译好的二进制文件路径。
qemu-system-arm \
    -cpu cortex-m3 \
    -machine mps2-an385 \
    -nographic \
    -S \
    -gdb tcp::1234 \
    --kernel "$1"
