# 在初赛中我们完成了基础版本的 dwarf 分析工具和 GDB 断点插桩工具. 
# 但是它们是独立的 2 组工具，使用不方便。
# 而且在初赛阶段我们专注于实现基本功能，所以没有考虑到代码可维护性和可读性的问题。
# 因此在决赛阶段，我们将 2 组工具合并为一组统一的工具集. 且对代码进行了重构和注释，提升可维护性和可读性。
# 为了方便测试，以及方便本工具的用户为其他异步运行时编写插件，本工具中的每一个小模块都是一个独立的 GDB 命令
# 可以作为调试流程中被自动调用的模块，也可以让用户手动调用。
# 另一个重大改变是，我们增加了大量测试用例。

# 重构进度：
# - dwarf_analyzer
#   - [x] export_map.py 导出 map.json -> find_poll_fn.py
#   - [ ] main.py -> GDB抽取出的dwarf解析模块
#   - [ ] 可视化依赖树
# - gdb_debugger / gdb_prolifer
#   - [ ] tracers
#   - [ ] 火焰图

# 下面是本工具的入口文件，定义了核心工具集的命令行
# 以及一些核心工具集的功能函数。



import sys
import os



# Get the directory of the current script.
# When this file is sourced in GDB, __file__ is defined, and we can use it
# to find the 'src' directory and add it to Python's path. This allows
# for robust importing of the 'core' module.
# 添加本文件夹到 GDB Python API 解释器的路径索引中（从而可以索引到 'core' 模块, `tokio`模块等）
script_dir = os.path.dirname(os.path.realpath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)


# define core utilities and register all GDB commands
# 注意，即使只 import 一个方法/函数/常量，整个模块都会被执行（执行的入口是 __init__.py）

# 0. 利用 `init-dwarf-analysis` 命令，初始化 Dwarf 分析器（包括 future 和 poll 函数之间转换的功能）
from core.init_dwarf_analysis import initDwarfAnalysisCommand # import will execute the whole module

# 1. 调用 core/dwarf.py 提供的终端命令，生成 async_dependencies.json

# 2. 利用 find-poll-fn 命令，找到所有 poll 函数
from core.find_poll_fn import FindPollFnCommand

# 3. 用户修改 json 文件，选择要跟踪的 poll 函数 （即修改 `async_backtrace` 选项，未来可以用 `jq` 工具做自动化）

# 4. 利用 `start-async-debug` 命令，
# 读取在第一步中生成的 json 文件，根据用户选择的 poll 函数，在第一步中生成的 json 文件中找到对应的 future
# 然后再次在第二步中生成的 json 里找到依赖这些 future 的所有 future（即future的父future，爷爷future，太爷爷future......），
# 然后再利用第一步中生成的 json 文件反解出这些 "future 家族们" 的 poll 函数，
# 最后对这些 poll 函数插桩
from core import StartAsyncDebugCommand

# 5. 利用 `inspect-async` 命令，获得异步调用栈。
# 这个命令的工作原理是：前面一步的插桩会记录函数调用/返回的时间戳，是哪个线程的，以及stacktrace.
# 每当poll函数触发的时候就将stacktrace信息更新到那个poll函数对应的thread中。
# 当用户调用这个命令的时候，会显示所有线程的stacktrace信息，并标注出每个线程的当前状态（running, blocked, waiting, etc.）
from core import InspectAsync # NOTE: 这个语句实际上是没有必要的，因为上一个 from import 语句已经执行了整个文件，所以已经注册了 InspectAsync 命令。这个语句实际上什么都不做

# 6. 利用 `dump-async-data` 命令，dump 异步数据为火焰图



# 用户手动调用 future analyzer 获得 json
# 命令行：
# python3 -m dwarf_analyzer.main tests/tokio_test_project/target/debug/tokio_test_project --json > results/async_dependencies.json
# 在 GDB dwarf 解析模块做好之后，再做自动调用 future 解析器的功能。




