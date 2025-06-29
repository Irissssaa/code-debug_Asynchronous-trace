#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <signal.h>
#include <linux/bpf.h>
#include <bpf/bpf.h>
#include "bpf_load.h"

#define MAX_ENTRIES	20
#define MAX_CPU		4
#define MAX_STARS	40

struct cpu_hist {
	long data[MAX_ENTRIES];
	long max;
};

static struct cpu_hist cpu_hist[MAX_CPU];

static void get_data(int fd)
{
	long key, value;
	int c, i;

	for (i = 0; i < MAX_CPU; i++)
		cpu_hist[i].max = 0;

	for (c = 0; c < MAX_CPU; c++) {
		for (i = 0; i < MAX_ENTRIES; i++) {
			key = c * MAX_ENTRIES + i;
			bpf_map_lookup_elem(fd, &key, &value);

			cpu_hist[c].data[i] = value;
			if (value > cpu_hist[c].max)
				cpu_hist[c].max = value;
		}
	}
}

int main(int argc, char **argv)
{
	char filename[256];

	snprintf(filename, sizeof(filename), "%s_kern.o", argv[0]);

	if (load_bpf_file(filename)) {
		printf("%s", bpf_log_buf);
		return 1;
	}

	while (1) {
		get_data(map_fd[1]);
		print_hist();
		sleep(5);
	}

	return 0;
}