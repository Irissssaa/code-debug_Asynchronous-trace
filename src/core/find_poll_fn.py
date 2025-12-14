# 功能：
# 基于 GDB 的符号表查询和 DWARF 类型解析功能
# 借助 `info functions` 命令
# 得到 函数名 - 返回类型 的映射关系

# 流程：
# 使用 `info functions` 命令获取所有函数，并过滤出返回类型为 `core::task::poll::Poll` 的函数
# 命令获取所有函数，并过滤出返回类型为 `core::task::poll::Poll` 的函数


import gdb
import re
import json
import os

from core.config import poll_type,result_path

class FindPollFnCommand(gdb.Command):
    """
    Finds all `poll` methods by parsing the output of `info functions`
    Use pipe + grep to make it faster.
    """
    def __init__(self):
        super().__init__("find-poll-fn", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        print("[rust-future-tracing] Finding all poll methods...")
        
        try:
            # 有的时候函数名或者返回值类型的范型里也会包含 `-> core::task::poll::Poll`，
            # 但这不意味着它们是 poll 函数。只有返回值类型是 `core::task::poll::Poll<...>` 的函数才是 poll 函数。
            # 此类问题的彻底解法是写一个 parser 将函数类型转换为带层级的格式化数据，
            # 或者改动 GDB 让它直接输出格式化数据（这个方案正在开发中）。
            # 目前采用一个 hack：
            # 我发现返回值类型的末尾总是有一个 `;` 符号作为函数类型的终止符
            # 因此利用正则表达式过滤出形如 `-> core::task::poll::Poll<任意类型>;` 的函数
            # 可以规避掉函数名或者返回值类型包含 `-> core::task::poll::Poll` 的函数的情况。
            # `info functions -> core::task::poll::Poll` 什么也没输出（原因未知），所以先用 `info functions` 获取所有函数
            # 然后再用正则表达式过滤出 poll 函数。
            output = gdb.execute("info functions", to_string=True)
            # info functions only query loaded symbols
            # 所以在未来支持断点组切换后，每切换一次符号表都要重新执行一次本命令
            poll_map = self._parse_poll_functions(output)
            
            # Write the map to a JSON file
            out_path = result_path + "poll_map.json"
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(poll_map, f, indent=2)
            
            print(f"[rust-future-tracing] Found {len(poll_map)} poll methods.")
            print(f"[rust-future-tracing] Poll map written to: {out_path}")
            print("[rust-future-tracing] Please edit this file to select the futures you want to trace.")

        except Exception as e:
            print(f"[rust-future-tracing] Error finding poll methods: {e}")

    def _parse_poll_functions(self, info_functions_output):
        """
        Parses the output of `info functions` to build the poll map.
        """
        poll_map = {}
        # This regex is designed to capture the full name of any function
        # that returns a Poll type.
        # 这是一个可以从 `info functions` 的输出中提取 `poll` 函数签名的正则表达式。这个表达式考虑到了 `info functions` 可能输出的行号和缩进。

        # ```regexp
        # ^\s*(?:\d+:\s+)?(.*?)( -> core::task::poll::Poll<.*>;)$
        # ```

        # 这个正则表达式被分成了两个主要的**捕获组**，这是与旧版本最关键的区别。

        # *   `^`: 匹配一行的开始。
        # *   `\s*`: 匹配行首任意数量的空白字符。
        # *   `(?:\d+:\s+)?`: 这是一个可选的**非捕获组**，用于匹配可能存在的行号（如 `310: `）。
        #     *   `\d+`: 匹配一个或多个数字（对应 `info functions` 输出的行号）。
        #     *   `:`: 匹配一个冒号。
        #     *   `\s+`: 匹配一个或多个空白字符。
        #     *   `?`: 使整个组成为可选的，这样没有行号的行也能匹配。
        # *   `(.*?)`: 这是**第一个捕获组**。
        #     *   `.*?` 是一个非贪婪匹配，它会匹配从行号之后到下一个模式（即 `-> core::task::poll::Poll`）之前的所有字符。
        #     *   **这个组捕获的是完整的函数名和参数列表**，例如 `hyper_util::rt::tokio::{impl#9}::poll(core::pin::Pin<&mut hyper_util::rt::tokio::TokioSleep>, *mut core::task::wake::Context)`。
        # *   `( -> core::task::poll::Poll<.*>;)`: 这是**第二个捕获组**。
        #     *   它精确匹配 `poll` 函数的返回类型签名，包括 `->`、`Poll` 类型以及结尾的分号。
        #     *   `.*` 会捕获 `Poll<...>` 中的泛型内容，例如 `()`。
        # *   `$`: 匹配一行的结束。

        regex_str = r'^\s*(\d+):\s+(.*?) -> {poll_type}<(.*)>;$'.format(poll_type=poll_type)
        print("[rust-future-tracing] Using regex: " + regex_str)
        fn_regex = re.compile(regex_str)
        filename = ""
        for line in info_functions_output.splitlines():
            # Check for file header lines
            file_line = re.match(r'^File (.*):$', line.strip())
            if file_line:
                filename = file_line.group(1)
                continue

            match = fn_regex.match(line.strip())
            if match:
                linenumber = match.group(1)  # poll函数行号
                fn_name = match.group(2)
                poll_generics = match.group(3) # 匹配 ( -> core::task::poll::Poll<这里的泛型内容>;)
                return_type = poll_type + "<" + poll_generics + ">"
                # Use filename:linenumber as the key
                key = f"{filename}:{linenumber}"
                poll_map[key] = {
                    "fn_name": fn_name,
                    "return_type": return_type,
                    "async_backtrace": False # 是否需要这个函数的异步函数调用栈
                }
            elif f"-> {poll_type}" in line:
                print(f"[rust-future-tracing] No match (which contains '-> {poll_type}') found for: {line}")
        return poll_map
FindPollFnCommand()
