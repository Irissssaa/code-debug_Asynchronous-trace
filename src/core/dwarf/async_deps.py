# NOTE: This is an independent module that is called from command line.
#
# FINAL CORRECTED VERSION:
# This version fixes a critical bug in the recursive dependency resolution that caused
# the dependency tree to be empty. The cycle detection logic (`seen` set) is now handled correctly.

import subprocess
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
import json
import os

@dataclass
class StructMember:
    name: str
    type: str
    offset: int
    size: int
    alignment: int
    is_artificial: bool = False
    decl_file: Optional[str] = None
    decl_line: Optional[int] = None

@dataclass
class Struct:
    name: str
    size: int
    alignment: int
    members: List[StructMember]
    is_async_fn: bool
    state_machine: bool
    type_id: Optional[str] = None
    locations: List[Dict[str, any]] = field(default_factory=list)

class DwarfAnalyzer:
    def __init__(self, binary_path: str):
        self.binary_path = binary_path
        # Key: type_id (str), a unique DIE offset. Value: Struct object.
        self.structs: Dict[str, Struct] = {}
        self.file_table: Dict[str, str] = {}
        self.current_struct: Optional[Struct] = None
        self.current_member: Optional[StructMember] = None

    def run_objdump(self) -> str:
        """Run objdump and return its output."""
        result = subprocess.run(['objdump', '--dwarf=info', self.binary_path],
                              capture_output=True, text=True, check=True)
        return result.stdout

    def parse_dwarf(self):
        """Parse DWARF information from objdump output (robust block detection)."""
        output = self.run_objdump()
        lines = output.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            if 'DW_TAG_compile_unit' in line:
                self.file_table = {}
                comp_unit_lines = [line]
                i += 1
                while i < len(lines) and 'DW_TAG_compile_unit' not in lines[i]:
                    comp_unit_lines.append(lines[i])
                    i += 1
                self._parse_file_table(comp_unit_lines)
                i -= len(comp_unit_lines)

            m = re.match(r'\s*<(\d+)><[0-9a-f]+>: Abbrev Number: .*?\(DW_TAG_structure_type\)', line)
            if m:
                struct_depth = int(m.group(1))
                struct_lines = [line]
                i += 1
                while i < len(lines):
                    l = lines[i]
                    m2 = re.match(r'\s*<(\d+)><[0-9a-f]+>: Abbrev Number:', l)
                    if m2 and int(m2.group(1)) <= struct_depth:
                        break
                    struct_lines.append(l)
                    i += 1
                self._parse_struct_block(struct_lines)
                continue
            i += 1

    def _parse_file_table(self, comp_unit_lines):
        comp_dir = ""
        for line in comp_unit_lines:
            if 'DW_AT_comp_dir' in line:
                match = re.search(r'DW_AT_comp_dir\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if match:
                    comp_dir = match.group(1).strip().strip('"')
                    break
        
        file_index = 1
        found_main_cu_name = False
        for line in comp_unit_lines:
            if 'DW_AT_name' in line:
                match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if match:
                    name = match.group(1).strip()
                    if not found_main_cu_name:
                        found_main_cu_name = True
                        continue
                    full_path = os.path.join(comp_dir, name) if comp_dir and not os.path.isabs(name) else name
                    self.file_table[str(file_index)] = full_path
                    file_index += 1

    def _parse_struct_block(self, struct_lines):
        name = None
        size = 0
        alignment = 0
        type_id = None
        is_async_fn = False
        state_machine = False
        members = []

        m = re.search(r'<[0-9a-f]+><([0-9a-f]+)>', struct_lines[0].lstrip())
        if m:
            type_id = m.group(1)

        for line in struct_lines:
            if name is None and 'DW_AT_name' in line:
                name_match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if name_match:
                    name = name_match.group(1).strip()
            if 'DW_AT_byte_size' in line:
                size_match = re.search(r'DW_AT_byte_size\s*:\s*(\d+)', line)
                if size_match:
                    size = int(size_match.group(1))
            if 'DW_AT_alignment' in line:
                align_match = re.search(r'DW_AT_alignment\s*:\s*(\d+)', line)
                if align_match:
                    alignment = int(align_match.group(1))
        
        if name:
            is_async_fn = re.search(r'async_fn_env|async_block_env', name) is not None
            state_machine = is_async_fn or re.search(r'Future|future', name, re.IGNORECASE) is not None
        
        member_block = []
        in_member = False
        for line in struct_lines[1:]:
            if 'DW_TAG_member' in line:
                if in_member and member_block:
                    member = self._parse_member_block(member_block)
                    if member: members.append(member)
                member_block = [line]
                in_member = True
            elif in_member:
                member_block.append(line)
        
        if in_member and member_block:
            member = self._parse_member_block(member_block)
            if member: members.append(member)

        if type_id:
            if name is None:
                name = f"anonymous_struct_<0x{type_id}>"

            struct = Struct(
                name=name,
                size=size,
                alignment=alignment,
                members=members,
                is_async_fn=is_async_fn,
                state_machine=state_machine,
                type_id=type_id
            )
            self.structs[type_id] = struct

    def _parse_member_block(self, member_lines):
        name = None
        type_str = 'unknown'
        offset = 0
        alignment = 0
        is_artificial = False
        decl_file = None
        decl_line = None
        for line in member_lines:
            if 'DW_AT_name' in line and name is None:
                name_match = re.search(r'DW_AT_name\s*:\s*(?:\(indirect string, offset: 0x[0-9a-f]+\):\s*)?(.+)', line)
                if name_match:
                    name = name_match.group(1).strip()
            if 'DW_AT_decl_file' in line:
                file_index_match = re.search(r'DW_AT_decl_file\s*:\s*(\d+)', line)
                if file_index_match:
                    decl_file = self.file_table.get(file_index_match.group(1))
            if 'DW_AT_decl_line' in line:
                line_match = re.search(r'DW_AT_decl_line\s*:\s*(\d+)', line)
                if line_match:
                    decl_line = int(line_match.group(1))
            if 'DW_AT_type' in line:
                type_match = re.search(r'DW_AT_type\s*:\s*<0x([0-9a-f]+)>', line)
                if type_match:
                    type_str = type_match.group(1)
            if 'DW_AT_data_member_location' in line:
                offset_match = re.search(r'DW_AT_data_member_location\s*:\s*(\d+)', line)
                if offset_match:
                    offset = int(offset_match.group(1))
            if 'DW_AT_alignment' in line:
                align_match = re.search(r'DW_AT_alignment\s*:\s*(\d+)', line)
                if align_match:
                    alignment = int(align_match.group(1))
            if 'DW_AT_artificial' in line:
                is_artificial = True
        
        if name:
            return StructMember(name=name, type=type_str, offset=offset, size=0,
                                alignment=alignment, is_artificial=is_artificial,
                                decl_file=decl_file, decl_line=decl_line)
        return None

    # FIXED: The recursive dependency resolution logic is corrected.
    def _resolve_deps_recursive(self, struct: Struct, seen: Set[str]) -> Set[str]:
        """
        Recursively find all unique future dependencies starting from a given struct.
        The `seen` set is used to prevent infinite loops in case of cyclic dependencies.
        """
        if not struct or not struct.type_id or struct.type_id in seen:
            return set()

        seen.add(struct.type_id)
        
        all_found_deps = set()

        for member in struct.members:
            child_type_id = member.type
            if child_type_id not in self.structs:
                continue
            
            child_struct = self.structs[child_type_id]

            if child_struct.state_machine:
                all_found_deps.add(child_type_id)
            
            # Always recurse to find transitive dependencies.
            # Pass the same 'seen' set down to maintain state across the entire traversal.
            all_found_deps.update(self._resolve_deps_recursive(child_struct, seen))
            
        return all_found_deps

    # FIXED: The initial call to the recursive helper now starts with an empty `seen` set.
    def build_dependency_tree(self) -> Dict[str, List[str]]:
        """Build a dependency tree of futures/state machines using DIE offsets."""
        self.parse_dwarf()
        tree: Dict[str, List[str]] = {}
        for type_id, struct in self.structs.items():
            if not struct.state_machine:
                continue
            
            # For each top-level state machine, start a fresh traversal with an empty 'seen' set.
            # The recursive function will handle cycle detection internally.
            deps_set = self._resolve_deps_recursive(struct, set())
            tree[type_id] = sorted(list(deps_set))
        return tree

    def output_json(self):
        dep_tree = self.build_dependency_tree()
        
        def struct_to_dict(struct):
            loc_set = set()
            for member in struct.members:
                if member.decl_file and member.decl_line:
                    loc_set.add((member.decl_file, member.decl_line))
            locations = [{'file': f, 'line': l} for f, l in sorted(list(loc_set))]
            
            return {
                'name': struct.name,
                'size': struct.size,
                'alignment': struct.alignment,
                'is_async_fn': struct.is_async_fn,
                'state_machine': struct.state_machine,
                'locations': locations,
                'members': [
                    {
                        'name': m.name, 'type_id_ref': m.type, 'offset': m.offset,
                        'size': m.size, 'alignment': m.alignment, 'is_artificial': m.is_artificial,
                        'decl_file': m.decl_file, 'decl_line': m.decl_line
                    } for m in struct.members
                ],
            }
        
        async_functions_by_offset = {
            type_id: struct_to_dict(struct)
            for type_id, struct in self.structs.items() if struct.is_async_fn
        }
        
        state_machines_by_offset = {
            type_id: struct_to_dict(struct)
            for type_id, struct in self.structs.items() if struct.state_machine
        }
        
        offset_to_name = {
            type_id: struct.name for type_id, struct in self.structs.items()
        }
        
        out = {
            'async_functions': async_functions_by_offset,
            'state_machines': state_machines_by_offset,
            'dependency_tree': dep_tree,
            'offset_to_name': offset_to_name
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))

def main():
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <binary_path> [--json]")
        sys.exit(1)
    binary_path = sys.argv[1]
    output_json = len(sys.argv) > 2 and sys.argv[2] == '--json'
    analyzer = DwarfAnalyzer(binary_path)
    if output_json:
        analyzer.output_json()

if __name__ == "__main__":
    main()
