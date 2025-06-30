## Rust异步函数跟踪工具

### 队伍信息

- 学校：北京工商大学；
- 队伍ID：T202510011995491；
- 队伍名：Async_Avengers；
- 赛题：proj158 支持Rust语言的源代码级内核调试工具；

### 项目描述

针对Rust语言的异步函数调用跟踪与调试难以及已有方法通用性差的问题，本项目设计基于GDB的白名单动态函数插桩跟踪与调试方法。我们旨在完成以下四个目标：

- 目标1：获取Rust异步代码与运行状态的对应关系；
- 目标2：获取Rust程序的Future依赖关系；
- 目标3：基于GDB实现支持白名单的异步函数跟踪框架；
- 目标4：Rust异步函数运行数据的可视化；

### 本仓库结构

```
.
├── docs/                               # 存放工具相关说明文档，包括实现思路、使用方法等
├── dwarf_analyzer/	                # 静态分析工具
	├── GDB_dwarf_analysis/		# 基于GDB dwarf解析模块的分析方案
	├── main.py			# 基于objdump工具的分析方案
├── gdb_debugger/                       # 动态调试工具
	├── main.py			# 基于 GDB 的函数插桩
	├── runtime_plugins/		# 实现的运行时特定插件
    ├── tracers/			# 提供的跟踪不同数据类型的 tracer
├── gdb_profiler/   			# 性能分析工具
├── results/        			# 分析结果输出
├── tests/          			# 测试项目  
└── README.md                           # 项目说明文档

```



### 工作日志

我们团队的工作日志在[这里](https://github.com/Irissssaa/code-debug_Asynchronous-trace/discussions)

