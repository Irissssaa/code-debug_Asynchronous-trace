#!/usr/bin/env python3
"""
Extract a subgraph from a GraphViz DOT call graph.

- Picks all nodes whose label matches a regex/pattern.
- Includes outgoing descendants up to a specified depth.
- Writes a standalone DOT with nodes + intra-subgraph edges.

Example:
  ./tools/dot_subgraph.py \
    --input tests/tokio_test_project/target/debug/deps/tokio_test_project-*.callgraph.dot \
    --pattern async_function_two \
    --depth 3 \
    --output tests/tokio_test_project/target/debug/deps/tokio_test_project_async_function_two_subgraph.dot

If --input is a glob, the first match is used.
"""
import argparse
import glob
import re
from collections import defaultdict, deque
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('--input', required=True, help='Path (or glob) to DOT file')
    p.add_argument('--pattern', required=True, help='Substring or regex to match node labels')
    p.add_argument('--depth', type=int, default=3, help='Descendant depth to include (default: 3)')
    p.add_argument('--output', required=True, help='Output DOT path')
    p.add_argument('--regex', action='store_true', help='Treat pattern as regular expression (default: substring)')
    return p.parse_args()


def read_dot(path: Path):
    text = path.read_text()
    lines = text.splitlines()
    node_labels = {}
    edges = defaultdict(set)

    current = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if '->' in stripped and stripped.endswith(';'):
            src_part, dst_part = stripped.split('->', 1)
            src = src_part.strip()
            dst = dst_part.rstrip(';').strip()
            edges[src].add(dst)
            continue
        if '[' in stripped and 'label=' in stripped:
            current = [stripped]
            collecting = not stripped.endswith('];')
            if not collecting:
                joined = ''.join(current)
                node_id = joined.split()[0]
                m = re.search(r'label="(.*)"', joined)
                label = m.group(1) if m else ''
                node_labels[node_id] = label
            continue
        if collecting:
            current.append(stripped)
            if stripped.endswith('];'):
                joined = ''.join(current)
                node_id = joined.split()[0]
                m = re.search(r'label="(.*)"', joined)
                label = m.group(1) if m else ''
                node_labels[node_id] = label
                collecting = False
                current = []

    return node_labels, edges


def select_subgraph(node_labels, edges, matcher, depth):
    starts = [n for n, lbl in node_labels.items() if matcher(lbl)]
    if not starts:
        raise SystemExit('No nodes matched the given pattern')

    selected = set(starts)
    q = deque((n, 0) for n in starts)
    while q:
        node, d = q.popleft()
        if d >= depth:
            continue
        for child in edges.get(node, ()):            
            if child not in selected:
                selected.add(child)
                q.append((child, d + 1))
    return selected


def write_dot(path: Path, selected, node_labels, edges, name='subgraph'):
    with path.open('w') as f:
        f.write(f'digraph "{name}" {{\n')
        for node in selected:
            label = node_labels.get(node, node)
            f.write(f'    {node} [label="{label}"];\n')
        for src in selected:
            for dst in edges.get(src, ()):            
                if dst in selected:
                    f.write(f'    {src} -> {dst};\n')
        f.write('}\n')


def main():
    args = parse_args()

    # Resolve input path
    matches = glob.glob(args.input)
    if not matches:
        raise SystemExit(f'No files match: {args.input}')
    inp = Path(matches[0])

    node_labels, edges = read_dot(inp)

    if args.regex:
        pattern = re.compile(args.pattern)
        matcher = lambda lbl: bool(pattern.search(lbl))
    else:
        matcher = lambda lbl: args.pattern in lbl

    selected = select_subgraph(node_labels, edges, matcher, args.depth)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_dot(out, selected, node_labels, edges, name=f'{args.pattern}_depth{args.depth}')
    print(f'Wrote subgraph with {len(selected)} nodes to {out}')


if __name__ == '__main__':
    main()
