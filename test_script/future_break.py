class FutureBreakpoints(gdb.Command):
    def __init__(self):
        super().__init__("break-futures", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        # 查找所有实现了Future的类型
        futures = gdb.execute("info types -q Future::poll", to_string=True)
        for line in futures.splitlines():
            if "::poll" in line:
                type_name = line.split("::poll")[0].strip()
                print(f"Setting breakpoint at {type_name}::poll")
                gdb.execute(f"break {type_name}::poll")

FutureBreakpoints()
