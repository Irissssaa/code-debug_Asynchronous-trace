import gdb
import json
import re

class Struct:
    def __init__(self, name, type_id, size, align, members, is_async_fn, state_machine):
        self.name = name
        self.type_id = type_id
        self.size = size
        self.align = align
        self.members = members  # dict: member_name -> (type, offset, size, align)
        self.is_async_fn = is_async_fn
        self.state_machine = state_machine

class RustFutureAnalyzer:
    def __init__(self):
        self.structs = {}  # name -> Struct
        self.type_id_to_struct = {}  # type_id -> Struct
        self.async_functions = {}  # name -> layout dict
        self.state_machines = {}  # name -> layout dict
        self.dependency_tree = {}  # name -> [child names]

    def analyze(self):
        self._collect_structs()
        self._extract_layouts()
        self._build_dependency_tree()
        self._output_json()

    def _collect_structs(self):
        # 解析 info types 输出，收集所有结构体类型
        output = gdb.execute("info types", to_string=True)
        type_re = re.compile(r'^[ \t]+([^\s]+)$', re.MULTILINE)
        all_types = []
        for line in output.splitlines():
            line = line.rstrip()
            if not line or line.startswith("File "):
                continue
            m = type_re.match(line)
            if m:
                all_types.append(m.group(1))
        print("All matched types (前20):", all_types[:20])

        for name in all_types:
            try:
                typ = gdb.lookup_type(name)
            except gdb.error:
                # 兜底尝试只用最后一级名
                try:
                    typ = gdb.lookup_type(name.split('::')[-1])
                except gdb.error:
                    print(f"lookup_type失败: {name}")
                    continue
            if typ.code != gdb.TYPE_CODE_STRUCT:
                continue
            type_id = id(typ)
            is_async_fn = bool(re.search(r'async_fn_env|async_block_env', name))
            state_machine = is_async_fn or bool(re.search(r'Future|future', name, re.IGNORECASE))
            members = {}
            for field in typ.fields():
                if field.is_base_class:
                    continue
                members[field.name] = {
                    "Type": str(field.type),
                    "Offset": field.bitpos // 8,
                    "Size": getattr(field.type, "sizeof", "unknown"),
                    "Alignment": getattr(field.type, "alignof", "unknown")
                }
            struct = Struct(
                name=name,
                type_id=type_id,
                size=typ.sizeof,
                align=getattr(typ, "alignof", "unknown"),
                members=members,
                is_async_fn=is_async_fn,
                state_machine=state_machine
            )
            self.structs[name] = struct
            self.type_id_to_struct[type_id] = struct
    
    def _extract_layouts(self):
        for name, struct in self.structs.items():
            layout = {
                "Size": f"{struct.size} bytes",
                "Alignment": f"{struct.align} bytes",
                "Members": struct.members
            }
            if struct.is_async_fn:
                self.async_functions[name] = layout
            if struct.state_machine:
                self.state_machines[name] = layout

    def _build_dependency_tree(self):
        # 递归构建依赖树，防止循环
        def resolve_deps_recursive(struct, visited, deps):
            if struct.name in visited:
                return
            visited.add(struct.name)
            for member in struct.members.values():
                member_type_str = member["Type"]
                # 只递归结构体类型
                child_struct = self.structs.get(member_type_str)
                if child_struct:
                    if child_struct.state_machine and child_struct.name not in deps:
                        deps.add(child_struct.name)
                    resolve_deps_recursive(child_struct, visited, deps)
        for name, struct in self.structs.items():
            if not struct.state_machine:
                continue
            visited = set()
            deps = set()
            resolve_deps_recursive(struct, visited, deps)
            self.dependency_tree[name] = list(deps)

    def _output_json(self):
        result = {
            "Async Functions": self.async_functions,
            "State Machines": self.state_machines,
            "dependency_tree": self.dependency_tree
        }
        with open("rust_future_analysis.json", "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("Rust future analysis written to rust_future_analysis.json")

class AnalyzeRustFuturesCommand(gdb.Command):
    """Analyze Rust async futures and output dependency tree as JSON."""
    def __init__(self):
        super().__init__("analyze_rust_futures", gdb.COMMAND_USER)
    def invoke(self, arg, from_tty):
        analyzer = RustFutureAnalyzer()
        analyzer.analyze()

AnalyzeRustFuturesCommand() 
