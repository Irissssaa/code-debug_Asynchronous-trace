from __future__ import annotations

import glob
import re
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, Optional, Set


class CallGraph:
    """Utility wrapper around an LLVM call graph exported as a DOT file."""

    def __init__(self, node_to_name: Dict[str, str], adjacency: Dict[str, Set[str]]):
        self._node_to_name = node_to_name
        self._adjacency = adjacency
        self._name_to_nodes: Dict[str, Set[str]] = defaultdict(set)
        for node_id, name in node_to_name.items():
            self._name_to_nodes[name].add(node_id)

    @classmethod
    def from_dot(cls, path: Path) -> Optional["CallGraph"]:
        if not path.exists():
            return None

        raw_node_labels: Dict[str, str] = {}
        edges = []

        text = path.read_text()
        lines = text.splitlines()

        current = []
        collecting = False
        for line in lines:
            stripped = line.strip()
            if "->" in stripped and stripped.endswith(";"):
                src_part, dst_part = stripped.split("->", 1)
                edges.append((src_part.strip(), dst_part.rstrip(";").strip()))
                continue

            if "[" in stripped and "label=" in stripped:
                current = [stripped]
                collecting = not stripped.endswith("];")
                if not collecting:
                    joined = "".join(current)
                    node_id = joined.split()[0]
                    label = cls._extract_label(joined)
                    raw_node_labels[node_id] = label
                continue

            if collecting:
                current.append(stripped)
                if stripped.endswith("];"):
                    joined = "".join(current)
                    node_id = joined.split()[0]
                    label = cls._extract_label(joined)
                    raw_node_labels[node_id] = label
                    collecting = False
                    current = []

        demangled_map = cls._demangle_labels(set(raw_node_labels.values()))
        node_to_name = {node_id: demangled_map.get(label, label) for node_id, label in raw_node_labels.items()}

        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for src, dst in edges:
            src_name = node_to_name.get(src)
            dst_name = node_to_name.get(dst)
            if not src_name or not dst_name:
                continue
            adjacency[src_name].add(dst_name)

        return cls(node_to_name, adjacency)

    @staticmethod
    def _extract_label(joined: str) -> str:
        match = re.search(r'label="(.*)"', joined)
        if not match:
            return joined
        label = match.group(1)
        if label.startswith("{") and label.endswith("}"):
            label = label[1:-1]
        return label

    @staticmethod
    def _demangle_labels(labels: Iterable[str]) -> Dict[str, str]:
        unique_labels = list(dict.fromkeys(labels))
        if not unique_labels:
            return {}

        try:
            proc = subprocess.run(
                ["rustfilt"],
                input="\n".join(unique_labels),
                capture_output=True,
                text=True,
                check=True,
            )
            demangled_lines = proc.stdout.splitlines()
            if len(demangled_lines) != len(unique_labels):
                # Fallback to identity mapping if counts mismatch
                return {label: label for label in unique_labels}
            return dict(zip(unique_labels, (line.strip() for line in demangled_lines)))
        except (subprocess.SubprocessError, FileNotFoundError):
            return {label: label for label in unique_labels}

    def descendants(self, start_names: Iterable[str], depth: int) -> Set[str]:
        """Return demangled descendants up to *depth* (excluding the start nodes)."""
        if depth <= 0:
            return set()

        visited: Set[str] = set()
        result: Set[str] = set()
        queue: deque = deque()

        for name in start_names:
            if name in self._adjacency:
                visited.add(name)
                queue.append((name, 0))

        while queue:
            node, dist = queue.popleft()
            if dist >= depth:
                continue
            for child in self._adjacency.get(node, ()):  # type: ignore[arg-type]
                if child not in visited:
                    visited.add(child)
                    result.add(child)
                    queue.append((child, dist + 1))

        return result

    def has_node(self, name: str) -> bool:
        return name in self._name_to_nodes


def find_call_graph(path_hint: str) -> Optional[CallGraph]:
    """Locate and load the call graph DOT file."""
    candidates = []
    project_root = Path(__file__).resolve().parents[2]
    if path_hint:
        hint_paths = []
        raw_hint = Path(path_hint)
        if raw_hint.is_absolute():
            hint_paths.append(raw_hint)
        else:
            hint_paths.append(project_root / raw_hint)
            hint_paths.append(Path.cwd() / raw_hint)

        seen: Set[Path] = set()
        for pattern in hint_paths:
            for match in glob.glob(str(pattern)):
                resolved = Path(match).resolve()
                if resolved not in seen:
                    candidates.append(resolved)
                    seen.add(resolved)
    else:
        search_roots = [project_root / "results", project_root]
        cwd = Path.cwd()
        if cwd not in search_roots:
            search_roots.append(cwd)

        seen: Set[Path] = set()
        for root in search_roots:
            if not root.exists():
                continue
            for match in root.glob("**/*.callgraph.dot"):
                resolved = match.resolve()
                if resolved not in seen:
                    candidates.append(resolved)
                    seen.add(resolved)
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for path in candidates:
        graph = CallGraph.from_dot(path)
        if graph:
            print(f"[rust-future-tracing] Loaded call graph from {path}")
            return graph

    print("[rust-future-tracing] WARNING: Unable to locate call graph DOT file.")
    return None
