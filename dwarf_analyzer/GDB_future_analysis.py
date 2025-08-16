# gdb_future_analyzer.py

import gdb
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any

# 使用 dataclass 优化数据结构，使其更清晰
@dataclass
class StructMember:
    name: str
    type_tag: Optional[str]
    offset: int
    size: Any
    align: Any

@dataclass
class Struct:
    name: str
    type_tag: str
    size: int
    align: Any
    members: Dict[str, StructMember]
    is_async_fn: bool
    state_machine: bool
    filename: Optional[str] = None
    line: Optional[int] = None

class RustFutureAnalyzer:
    def __init__(self):
        # 键全部切换为使用 type_tag，等同于 objdump 脚本中的 DIE Offset 功能
        self.structs: Dict[str, Struct] = {}  # type_tag -> Struct
        self.async_functions: Dict[str, Struct] = {}
        self.state_machines: Dict[str, Struct] = {}
        self.dependency_tree: Dict[str, List[str]] = {}
        self.tag_to_name: Dict[str, str] = {}

    def analyze(self):
        print("开始分析: 收集所有结构体类型...")
        self._collect_structs()
        print(f"收集完成: 共找到 {len(self.structs)} 个结构体。")
        
        print("开始构建依赖树...")
        self._build_dependency_tree()
        print("依赖树构建完成。")

        print("正在生成 JSON 输出...")
        self._output_json()

    def _collect_structs(self):
        # info types 仍然是获取 GDB 已知类型列表的直接方式
        output = gdb.execute("info types", to_string=True)
        # 正则表达式需要稳健，以处理各种类型名称
        type_re = re.compile(r'^(?:\d+:\s*)?((?:[\w_]+::)+<.+>|[\w_:]+)\s*;?\s*$')
        
        all_type_names = set()
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("File "):
                continue
            # 尝试从行中提取类型名称
            if line.endswith(';'):
                line = line[:-1]
            # 简化匹配，GDB的输出格式可能不那么规则
            parts = line.split()
            if len(parts) > 0:
                # 通常类型名在行尾，前面可能有行号和冒号
                type_name = parts[-1]
                if '::' in type_name or '<' in type_name:
                    all_type_names.add(type_name)

        print(f"通过 'info types' 初步匹配到 {len(all_type_names)} 个可能的类型名称。")

        for name in list(all_type_names):
            try:
                typ = gdb.lookup_type(name)
                if typ.code != gdb.TYPE_CODE_STRUCT:
                    continue
                
                # 使用 type.tag 作为稳定且唯一的标识符
                # 它类似于 DWARF DIE Offset 的作用
                type_tag = typ.tag
                if not type_tag or type_tag in self.structs:
                    continue

                is_async_fn = 'async_fn_env' in type_tag or 'async_block_env' in type_tag
                state_machine = is_async_fn or 'Future' in name or 'future' in name

                members = {}
                for field in typ.fields():
                    if field.is_base_class or field.name is None:
                        continue
                    
                    member_type = field.type.strip_td()
                    members[field.name] = StructMember(
                        name=field.name,
                        type_tag=getattr(member_type, 'tag', str(member_type)),
                        offset=field.bitpos // 8,
                        size=getattr(member_type, "sizeof", "unknown"),
                        align=getattr(member_type, "alignof", "unknown")
                    )

                struct = Struct(
                    name=name,
                    type_tag=type_tag,
                    size=typ.sizeof,
                    align=getattr(typ, "alignof", "unknown"),
                    members=members,
                    is_async_fn=is_async_fn,
                    state_machine=state_machine,
                    filename=typ.filename,
                    line=typ.line
                )
                self.structs[type_tag] = struct
                self.tag_to_name[type_tag] = name # 建立 tag -> name 映射
                
                if is_async_fn:
                    self.async_functions[type_tag] = struct
                if state_machine:
                    self.state_machines[type_tag] = struct

            except gdb.error as e:
                # print(f"警告: gdb.lookup_type('{name}') 失败: {e}")
                continue

    def _build_dependency_tree(self):
        for struct_tag, struct in self.structs.items():
            if not struct.state_machine:
                continue
            
            # 使用 Set 来自动处理重复项并提高性能
            deps: Set[str] = set()
            visited: Set[str] = {struct_tag} # 防止自循环
            
            # 使用栈进行深度优先搜索，避免递归过深
            stack: List[Struct] = [struct]
            while stack:
                current_struct = stack.pop()
                for member in current_struct.members.values():
                    member_type_tag = member.type_tag
                    if not member_type_tag or member_type_tag in visited:
                        continue
                    
                    child_struct = self.structs.get(member_type_tag)
                    if child_struct:
                        visited.add(member_type_tag)
                        # 无论子结构是不是状态机，都继续深入探索其成员
                        stack.append(child_struct)
                        # 只有当子结构是状态机时，才将其加入依赖列表
                        if child_struct.state_machine:
                            deps.add(member_type_tag)

            self.dependency_tree[struct_tag] = list(deps)

    def _struct_to_dict(self, struct: Struct) -> Dict:
        """辅助函数，将 Struct 对象转换为符合 objdump 脚本输出格式的字典。"""
        return {
            "name": struct.name,
            "size": struct.size,
            "alignment": struct.align,
            "is_async_fn": struct.is_async_fn,
            "state_machine": struct.state_machine,
            "locations": [{'file': struct.filename, 'line': struct.line}] if struct.filename else [],
            "members": [
                {
                    "name": m.name,
                    "type": m.type_tag, # 在这里我们用 type_tag 模拟 type_id (DIE Offset)
                    "offset": m.offset,
                    "size": m.size,
                    "alignment": m.align
                } for m in struct.members.values()
            ],
            "type_id": struct.type_tag # 在 GDB 脚本中，type_tag 是我们的 "type_id"
        }

    def _output_json(self):
        # 构建与 objdump 脚本格式完全一致的输出
        async_functions_by_tag = {
            tag: self._struct_to_dict(struct) 
            for tag, struct in self.async_functions.items()
        }
        
        state_machines_by_tag = {
            tag: self._struct_to_dict(struct)
            for tag, struct in self.state_machines.items()
        }
        
        result = {
            "async_functions": async_functions_by_tag,
            "state_machines": state_machines_by_tag,
            "dependency_tree": self.dependency_tree,
            "offset_to_name": self.tag_to_name # GDB 中是 tag_to_name
        }
        
        file_path = "rust_future_analysis_gdb.json"
        with open(file_path, "w", encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Rust future analysis written to {file_path}")


class AnalyzeRustFuturesCommand(gdb.Command):
    """Analyze Rust async futures and output dependency tree as JSON."""
    def __init__(self):
        super().__init__("analyze-rust-futures", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        # 确保已加载调试对象
        if not gdb.current_progspace().filename:
            print("错误: 请先加载一个带调试信息的可执行文件 (e.g., 'file my_binary')。")
            return
            
        analyzer = RustFutureAnalyzer()
        analyzer.analyze()

# 注册命令
AnalyzeRustFuturesCommand()AnalyzeRustFuturesCommand() 
