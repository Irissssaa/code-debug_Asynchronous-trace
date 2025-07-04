## 基于GDB的Rust异步函数调试方法

### 队伍信息

- 学校院系：北京工商大学计算机系；
- 队员：曾小红，张弈帆，董嘉誉；
- 指导老师：吴竞邦；
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
├── docs/                               # 存放工具相关说明文档，包括实现思路、使用方法等，以及参赛文档
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

### 初赛文档
我们的初赛文档在[这里](https://github.com/Irissssaa/code-debug_Asynchronous-trace/blob/main/docs/%E5%88%9D%E8%B5%9B%E6%96%87%E6%A1%A3-Proj158-%E6%94%AF%E6%8C%81Rust%E8%AF%AD%E8%A8%80%E7%9A%84%E6%BA%90%E4%BB%A3%E7%A0%81%E7%BA%A7%E5%86%85%E6%A0%B8%E8%B0%83%E8%AF%95%E5%B7%A5%E5%85%B7.md)

### 工作日志

我们团队的工作日志在[这里](https://github.com/Irissssaa/code-debug_Asynchronous-trace/discussions)

### 项目进度

| 目标 | 完成情况 | 说明                                                         |
| :--: | :------: | :----------------------------------------------------------- |
|  1   |   完成   | ✓ 实现 GDB Python 脚本插件加载机制<br />✓ 实现自动在函数进入和返回处打断点的插件<br />✓ 实现在断点触发后自动收集异步函数运行状态的插件<br />✓ 实现从异步函数名对应到 poll 函数的插件2完成 |
|  2   | 部分完成 | ✓ objdump 输出信息解析<br />[ ] 用 GDB 代替 objdump<br /> ✓ 构建异步函数依赖关系树<br />✓ 解析源代码中异步函数和符号表中poll函数的对应关系 |
|  3   |  未完成  | [ ] 实现异步程序跟踪框架（方便的异步运行时插桩，方便的异步运行时状态获取功能）<br />[ ] 实现tracer（函数参数、全局/本地变量，栈回溯获取等）<br />[ ] 内核态适配（拟embassy）<br />[ ] 用户态适配（tokio） |
|  4   |   完成   | ✓ 利用 GDB 插桩功能生成和绘制火焰图相关的事件<br />✓ Chrome Trace Event 格式 json 输出 |

