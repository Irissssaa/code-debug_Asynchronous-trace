#include "bpf.h"
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

int sys_bpf(int cmd, union bpf_attr *attr, size_t size) {
  printf("cmd = %d\n", cmd);
  return syscall(SYS_bpf, cmd, attr, size);
}


int 
bpf_create_map(enum bpf_map_type map_type, uint32_t key_size, uint32_t value_size, uint32_t max_entries) {
    union bpf_attr attr = {
        .map_type = map_type,
        .key_size = key_size,
        .value_size = value_size,
        .max_entries = max_entries,
    };
    return sys_bpf(BPF_MAP_CREATE, &attr, sizeof(attr));
}

int
bpf_lookup_elem(int fd, const void *key, void *value) {
    union bpf_attr attr = {
        .map_fd = fd,
        .key = (uint64_t) key,
        .value = (uint64_t) value,
    };
    return sys_bpf(BPF_MAP_LOOKUP_ELEM, &attr, sizeof(attr));
}

int
bpf_update_elem(int fd, const void *key, const void *value, uint64_t flags) {
    union bpf_attr attr = {
        .map_fd = fd,
        .key = (uint64_t) key,
        .value = (uint64_t) value,
        .flags = flags,
    };
    return sys_bpf(BPF_MAP_UPDATE_ELEM, &attr, sizeof(attr));
}

int
bpf_delete_elem(int fd, const void *key) {
    union bpf_attr attr = {
        .map_fd = fd,
        .key = (uint64_t) key,
    };
    return sys_bpf(BPF_MAP_DELETE_ELEM, &attr, sizeof(attr));
}

int
bpf_get_next_key(int fd, const void *key, void *next_key) {
    union bpf_attr attr = {
        .map_fd = fd,
        .key = (uint64_t) key,
        .next_key = (uint64_t) next_key,
    };
    return sys_bpf(BPF_MAP_GET_NEXT_KEY, &attr, sizeof(attr));
}

int
bpf_prog_load_ex(void *prog, uint32_t prog_size, struct bpf_map_fd_entry *map_array, uint32_t map_array_len) {
    union bpf_attr attr = {
        .prog = (uint64_t) prog,
        .prog_size = prog_size,
        .map_array_len = map_array_len,
        .map_array = map_array,
    };
    return sys_bpf(BPF_PROG_LOAD_EX, &attr, sizeof(attr));
}

int bpf_prog_attach(const char *target, uint32_t str_len, int prog_fd) {
  union bpf_attr attr = {
      .target = target,
      .str_len = str_len,
      .prog_fd = prog_fd,
  };
  printf("bpf prog attach size: %lld\n", sizeof(attr));
  return sys_bpf(BPF_PROG_ATTACH, &attr, sizeof(attr));
}
