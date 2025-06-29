#ifndef __LIBS_BPF_H__
#define __LIBS_BPF_H__

#include <inttypes.h>
#include <stdint.h>
#include <syscall.h>

// see Linux kernel /include/uapi/linux/bpf.h

typedef uint64_t size_t;

enum bpf_cmd {
  BPF_MAP_CREATE,
  BPF_MAP_LOOKUP_ELEM,
  BPF_MAP_UPDATE_ELEM,
  BPF_MAP_DELETE_ELEM,
  BPF_MAP_GET_NEXT_KEY,
  BPF_PROG_LOAD,
  BPF_OBJ_PIN,
  BPF_OBJ_GET,
  BPF_PROG_ATTACH,
  BPF_PROG_DETACH,
  BPF_PROG_TEST_RUN,
  BPF_PROG_RUN = BPF_PROG_TEST_RUN,
  BPF_PROG_GET_NEXT_ID,
  BPF_MAP_GET_NEXT_ID,
  BPF_PROG_GET_FD_BY_ID,
  BPF_MAP_GET_FD_BY_ID,
  BPF_OBJ_GET_INFO_BY_FD,
  BPF_PROG_QUERY,
  BPF_RAW_TRACEPOINT_OPEN,
  BPF_BTF_LOAD,
  BPF_BTF_GET_FD_BY_ID,
  BPF_TASK_FD_QUERY,
  BPF_MAP_LOOKUP_AND_DELETE_ELEM,
  BPF_MAP_FREEZE,
  BPF_BTF_GET_NEXT_ID,
  BPF_MAP_LOOKUP_BATCH,
  BPF_MAP_LOOKUP_AND_DELETE_BATCH,
  BPF_MAP_UPDATE_BATCH,
  BPF_MAP_DELETE_BATCH,
  BPF_LINK_CREATE,
  BPF_LINK_UPDATE,
  BPF_LINK_GET_FD_BY_ID,
  BPF_LINK_GET_NEXT_ID,
  BPF_ENABLE_STATS,
  BPF_ITER_CREATE,
  BPF_LINK_DETACH,
  BPF_PROG_BIND_MAP,
  // custom commands
  BPF_PROG_LOAD_EX = 1000,
};

enum bpf_map_type {
  BPF_MAP_TYPE_UNSPEC,
  BPF_MAP_TYPE_HASH,
  BPF_MAP_TYPE_ARRAY,
  BPF_MAP_TYPE_PROG_ARRAY,
  BPF_MAP_TYPE_PERF_EVENT_ARRAY,
  BPF_MAP_TYPE_PERCPU_HASH,
  BPF_MAP_TYPE_PERCPU_ARRAY,
  BPF_MAP_TYPE_STACK_TRACE,
  BPF_MAP_TYPE_CGROUP_ARRAY,
  BPF_MAP_TYPE_LRU_HASH,
  BPF_MAP_TYPE_LRU_PERCPU_HASH,
  BPF_MAP_TYPE_LPM_TRIE,
  BPF_MAP_TYPE_ARRAY_OF_MAPS,
  BPF_MAP_TYPE_HASH_OF_MAPS,
  BPF_MAP_TYPE_DEVMAP,
  BPF_MAP_TYPE_SOCKMAP,
  BPF_MAP_TYPE_CPUMAP,
  BPF_MAP_TYPE_XSKMAP,
  BPF_MAP_TYPE_SOCKHASH,
  BPF_MAP_TYPE_CGROUP_STORAGE,
  BPF_MAP_TYPE_REUSEPORT_SOCKARRAY,
  BPF_MAP_TYPE_PERCPU_CGROUP_STORAGE,
  BPF_MAP_TYPE_QUEUE,
  BPF_MAP_TYPE_STACK,
  BPF_MAP_TYPE_SK_STORAGE,
  BPF_MAP_TYPE_DEVMAP_HASH,
  BPF_MAP_TYPE_STRUCT_OPS,
  BPF_MAP_TYPE_RINGBUF,
  BPF_MAP_TYPE_INODE_STORAGE,
  BPF_MAP_TYPE_TASK_STORAGE,
  BPF_MAP_TYPE_BLOOM_FILTER,
};

struct bpf_map_fd_entry {
  const char *name;
  uint32_t fd;
};

union bpf_attr {
  struct {
    uint32_t map_type;
    uint32_t key_size;
    uint32_t value_size;
    uint32_t max_entries;
    // more...
  };

  struct {
    uint32_t map_fd;
    uint64_t key;
    union {
      uint64_t value;
      uint64_t next_key;
    };
    uint64_t flags;
  };

  // for custom BPF_PROG_LOAD_EX
  struct {
    uint64_t prog;
    uint32_t prog_size;
    uint32_t map_array_len;
    struct bpf_map_fd_entry *map_array;
  };

  // for custom BPF_PROG_ATTACH
  struct {
    const char *target;
    uint32_t str_len;
    uint32_t prog_fd;
  };
};

int sys_bpf(int cmd, union bpf_attr *attr, size_t size);

int bpf_create_map(enum bpf_map_type map_type, uint32_t key_size,
                   uint32_t value_size, uint32_t max_entries);
int bpf_lookup_elem(int fd, const void *key, void *value);
int bpf_update_elem(int fd, const void *key, const void *value, uint64_t flags);
int bpf_delete_elem(int fd, const void *key);
int bpf_get_next_key(int fd, const void *key, void *next_key);

int bpf_prog_load_ex(void *prog, uint32_t prog_size,
                     struct bpf_map_fd_entry *map_array,
                     uint32_t map_array_len);
int bpf_prog_attach(const char *target, uint32_t str_len, int fd);

#endif // __LIBS_BPF_H__
