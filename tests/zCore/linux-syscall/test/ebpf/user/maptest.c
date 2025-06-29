
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <syscall.h>
#include <inttypes.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <string.h>
#include <assert.h>
#include "bpf.h"

#define MAX_ENTRIES 512

void test_bpf_array_map() {
    int key;
    uint64_t value;
    printf("Start test on bpf array map, this is a just a test in user space\n");
    int fd = bpf_create_map(BPF_MAP_TYPE_ARRAY, sizeof(key), sizeof(value), MAX_ENTRIES);
    assert(fd > 0);
    printf("bpf array with fd: %d created\n", fd);

    key = 3;
    assert(bpf_lookup_elem(fd, &key, &value) == 0);
    assert(value == 0);
    printf("test lookup_elem index=%d, get value=%ld\n", key, value);

    key = 3;
    value = 0x1122334455667788LL;
    assert(bpf_update_elem(fd, &key, &value, 0) == 0);
    printf("test update_elem index=%d to %ld, and get value=%ld\n", key, 0x1122334455667788L, value);

    key = MAX_ENTRIES + 1;
    assert(bpf_update_elem(fd, &key, &value, 0) < 0); // this should fail
    printf("test index exceed max_entry\n");

    key = 3;
    assert(bpf_delete_elem(fd, &key) < 0); // this should fail
    printf("test delete index=%d, this should fail since you cannot delete an array entry \n", key);

    assert(bpf_lookup_elem(fd, &key, &value) == 0);
    assert(value == 0x1122334455667788LL);
    printf("check index=%d again, and we should get a valid value=%ld \n", key, value);
    printf("bpf array tests PASSED\n");
}


void test_bpf_hashmap() {
    uint64_t key, value, next_key;

    printf("Start test on bpf hash map, this is a just a test in user space\n");

    int fd = bpf_create_map(BPF_MAP_TYPE_HASH, sizeof(key), sizeof(value), MAX_ENTRIES);
    assert(fd > 0);
    printf("bpf hash map with fd: %d created\n", fd);

    for (int i = 1; i <= 10; ++i) {
        key = i * 0x2348fe12 + (86514 ^ i);
        value = i;
        printf("put kv: (%lx, %ld)\n", key, value);
        assert(bpf_update_elem(fd, &key, &value, 0) == 0);
    }

    key = 0;
    while (bpf_get_next_key(fd, &key, &next_key) == 0) {
        key = next_key;
        assert(bpf_lookup_elem(fd, &key, &value) == 0);
        printf("get kv: (%lx, %ld)\n", key, value);
    }

    key = 1 * 0x2348fe12 + (86514 ^ 1);
    assert(bpf_delete_elem(fd, &key) == 0); // this should fail
    printf("test delete key=%ld \n", key);
    assert(bpf_lookup_elem(fd, &key, &value) < 0);
    printf("try get key=%ld again, this should fail\n", key);


    printf("bpf hashmap tests OK\n");
}


int main() {

    test_bpf_array_map();

    test_bpf_hashmap();

    printf("ALL TEST PASSED!\n");


    return 0;
}
