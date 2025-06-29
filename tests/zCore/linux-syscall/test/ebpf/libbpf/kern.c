#include <linux/version.h>
#include <linux/ptrace.h>
#include <bpf/bpf_helpers.h>

#define MAX_ENTRIES	20
#define MAX_CPU		4

struct bpf_map_def SEC("maps") my_map = {
	.type = BPF_MAP_TYPE_ARRAY,
	.key_size = sizeof(int),
	.value_size = sizeof(u64),
	.max_entries = MAX_CPU,
};

SEC("kprobe/trace_preempt_off")
int bpf_prog1(struct pt_regs *ctx)
{
	int cpu = bpf_get_smp_processor_id();
	u64 *ts = bpf_map_lookup_elem(&my_map, &cpu);

	if (ts)
		*ts = bpf_ktime_get_ns();

	return 0;
}