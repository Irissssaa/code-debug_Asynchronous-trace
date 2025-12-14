# dwarf-analyzer 开发日志

之前版本（代码：dwarf_analyzer/main.py 文档：async.md）可以解析自己写的极简runtime的 future 依赖，但是无法解析出tokio爬虫例子
（tokio_test_project）里的`reqwest::get`函数。该函数在本工具生成的 poll 函数列表中存在，但是在 future 依赖列表中不存在。

因此我希望用其他方法（之前单纯看 objdump 的输出），观察异步rust程序生成的 dwarf 信息，希望能对异步rust的编译产物获得一些更高层的理解。

首先尝试用 GDB 输出 dwarf 信息。查阅 GDB 文档，发现以下命令：

```
set debug dwarf-die
               Dump DWARF DIEs after they are read in. The value is the number of nesting
               levels to print. A value of zero turns off the display.

show debug dwarf-die
               Show the current state of DWARF DIE debugging.

set debug dwarf-line
               Turns on or off display of debugging messages related to reading DWARF line
               tables. The default is 0 (off). A value of 1 provides basic information. A value
               greater than 1 provides more verbose information.

show debug dwarf-line
               Show the current state of DWARF line table debugging.

set debug dwarf-read
               Turns on or off display of debugging messages related to reading DWARF debug
               info. The default is 0 (off). A value of 1 provides basic information. A value
               greater than 1 provides more verbose information.

show debug dwarf-read
               Show the current state of DWARF reader debugging.

```
我试了下 `show debug dwarf-die`, 输出结果的格式化程度比 objdump 还要差，不适合作为参考例子。

然后我想到，rust编译器是基于 llvm 的，那么 llvm 的 dwarf dump 工具会不会提供一些新功能（比如格式化输出，或者更方便地查找某个结构体），可惜目前没有。在 github 上有一个 llvm-dwarfdump json 输出的 issue: https://github.com/llvm/llvm-project/issues/147850 , 但是他们的工作才刚起步。

然后我尝试了 GUI DWARF 阅读器 [dwex](https://github.com/sevaa/dwex) ：

> 注：在 ubuntu 24.04 里不能在系统环境下直接安装 Python 包，需要先设置一个虚拟环境，再调用虚拟环境内的 `python3` 解释器安装 `dwex`：
> mkdir dwex &&
> python3 -m venv venv
> cd venv
> ./venv/bin/python3 -m pip install dwex
> dwex

```
namespace: get
  ▸ subprogram: {async_fn#0}<&str>
  ▾ structure_type: {async_fn_env#0}<&str>
    ▾ variant_part
        member: __state
        ▾ variant
            member: 0
        ▾ variant
            member: 1
        ▾ variant
            member: 2
        ▾ variant
            member: 3
            ▾ structure_type: Unresumed
                member: url
            ▾ structure_type: Returned
                member: url
            ▾ structure_type: Panicked
                member: url
            ▾ structure_type: Suspend0
                member: __0
                member: __1
                member: __awaitee
                member: __3
                member: url

pointer_type: &mut reqwest::async_impl::client::Pending
base_type: u64
pointer_type: alloc::boxed::Box<reqwest::async_impl::client::PendingR...>
```

其次我还找到如下这样只有structure_type没有subprogram的：

```
▾ namespace: reqwest
  ▾ namespace: get
    ▾ structure_type: {async_fn_env#0}<&str>
      ▸ variant_part
      ▸ structure_type: Unresumed
      ▸ structure_type: Returned
      ▸ structure_type: Panicked
      ▸ structure_type: Suspend0
```

我猜测在这个编译单元中，代码使用了reqwest::get::{async_fn#0} 的上下文，但并没有调用这个函数本身。

我还找到一个更具迷惑性的例子。

源代码如下（这是旧版的 future_executor_test 测试用例）：

```rust
use core::future::{Future, poll_fn};
use core::pin::Pin;
use core::task::{Context, Poll, Waker};

// simple no-std future example

fn main() {
    spawn(test1());
    spawn(test2());
    spawn(test3());
    run();
}

pub struct Executor {
    pub tasks: Vec<Pin<Box<dyn Future<Output = ()> + Send + 'static>>>,
}

static mut EXECUTOR: Executor = Executor { tasks: Vec::new() };

fn spawn<F>(f: F)
where
    F: Future<Output = ()> + Send + 'static,
{
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(Box::pin(f));
}

fn pick_next_task() -> Option<Pin<Box<dyn Future<Output = ()> + Send + 'static>>> {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.pop()
}

fn put_prev_task(task: Pin<Box<dyn Future<Output = ()> + Send + 'static>>) {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(task)
}

async fn yield_now() {
    let mut flag = false;
    poll_fn(|_cx| {
        if !flag {
            flag = true;
            Poll::Pending
        } else {
            Poll::Ready(())
        }
    })
    .await;
}

fn run() {
    let waker = Waker::noop();
    let mut cx = Context::from_waker(&waker);
    loop {
        if let Some(mut task) = pick_next_task() {
            match task.as_mut().poll(&mut cx) {
                Poll::Pending => {
                    put_prev_task(task);
                }
                Poll::Ready(_) => {}
            }
        } else {
            break;
        }
    }
}

async fn test1() {
    println!("run test task 1");
    yield_now().await;
    println!("run test task 1 done");
}

async fn test2() {
    println!("run test task 2");
}

async fn test3() {
    println!("run test task 3");
} 
```

Cargo.toml:

```toml
[package]
name = "future_executor_test"
version = "0.1.0"
edition = "2021"

[dependencies]

[profile.dev]
debug = 2 
```
同一个 test1 的异步函数出现了两次。第一次：

```
13bwrj36s0cx020k8frbf0ias
▾ namespace: Future_executor_test
  variable: EXECUTOR
  ▸ structure_type: Executor
  subprogram: main
  ▾ subprogram: pick_next_task
    ▸ lexical_block
  subprogram: put_prev_task
  subprogram: yield_now
  subprogram: run
  subprogram: test1
  subprogram: test2
  subprogram: test3
  ▾ namespace: yield_now
  ▾ namespace: test1
    ▾ structure_type: {async_fn_env#0}
      ▾ variant_part
        ▸ structure_type: Unresumed
        ▸ structure_type: Returned
        ▸ structure_type: Panicked
        ▸ structure_type: Suspend0
        ▸ structure_type: Suspend1
        ▸ structure_type: Suspend2
  ▾ namespace: test2
    ▾ structure_type: {async_fn_env#0}
      ▾ variant_part
        ▸ structure_type: Unresumed
        ▸ structure_type: Returned
        ▸ structure_type: Panicked
        ▸ structure_type: Suspend0
  ▾ namespace: test3
    ▾ structure_type: {async_fn_env#0}
      ▾ variant_part
        ▸ structure_type: Unresumed
        ▸ structure_type: Returned
        ▸ structure_type: Panicked
▸ namespace: alloc
▸ namespace: core

```

第二次：
```
▸ cv6qjq4ol733uzx1soc8xp3fp
  variable: <future_executor_test::test1::{async_fn_env#0} as core::future::future::Future>::{vtable}
  ▾ structure_type: <future_executor_test::test1::{async_fn_env#0} as core::future::future::Future>::{vtable_type}
    pointer_type: *const ()
    base_type: ()
    base_type: usize
  ▾ namespace: future_executor_test
    ▾ namespace: test1
      ▾ structure_type: {async_fn_env#0}
        ▾ variant_part
          member: __state
          ▾ variant
            member: 0
          ▾ variant
            member: 1
          ▾ variant
            member: 2
          ▾ variant
            member: 3
          ▾ structure_type: Unresumed
          ▾ structure_type: Returned
          ▾ structure_type: Panicked
          ▾ structure_type: Suspend0
          ▾ structure_type: Suspend1
          ▾ structure_type: Suspend2
      ▾ subprogram: {async_fn#0}
        formal_parameter
        variable: _task_context
        ▾ lexical_block
        ▾ lexical_block
        ▾ lexical_block
    ▾ namespace: yield_now
      ▾ structure_type: {async_fn_env#0}
      ▾ namespace: {async_fn#0}
      ▾ subprogram: {async_fn#0}
    ▾ namespace: test2
      ▾ structure_type: {async_fn_env#0}
      ▾ subprogram: {async_fn#0}
    ▾ namespace: test3
      ▾ structure_type: {async_fn_env#0}
      ▾ subprogram: {async_fn#0}
    ▾ subprogram: spawn<future_executor_test::test1::{async_fn_env#0}>
    ▾ subprogram: spawn<future_executor_test::test2::{async_fn_env#0}>
    ▾ subprogram: spawn<future_executor_test::test3::{async_fn_env#0}>
    ▸ structure_type: Executor
  base_type: u8
  base_type: bool
▾ namespace: core
  pointer_type: &mut bool
  variable: <future_executor_test::test2::{async_fn_env#0} as core::future::future::Future>::{vtable}
  ▾ structure_type: <future_executor_test::test2::{async_fn_env#0} as core::future::future::Future>::{vtable_type}
  variable: <future_executor_test::test3::{async_fn_env#0} as core::future::future::Future>::{vtable}
```

注意第一次“出现”中：
1. subprogram 是无法展开的（没有▾ 或▸ ）
2. namespace: test1 和 subprogram: test1 是 **兄弟** 关系不是 **父子**关系，而第二次出现的是父子关系，即 namespace: test1 的子结点包含 subprogram: {async_fn#0} 和 structure_type: {async_fn#0}
3. namespace: test1 中只有 {async_fn_env#0} 没有 async_fn 和 structure_type （也就是说只有必包函数的上下文，没有必包函数本身和必包函数的状态机）

也就是说，第一个编译单元中出现的 test1 相关 DIE 想表达的意思是“本源文件中存在 test1 函数这个函数签名（subprogram）test1 函数的上下文，但是并没有这个函数的具体实现”，第二个编译单元中出现的 test1 相关 DIE 结构才是我们想要的：namespace: test1 里包含一个闭包函数和这个闭包函数的上下文。

最后一个迷惑性的例子，源代码是新版本的 future_executor_test：
```rust
use core::future::{Future, poll_fn};
use core::pin::Pin;
use core::task::{Context, Poll, Waker};

// simple no-std future example

fn main() {
    spawn(test1());
    spawn(test2());
    spawn(test3());
    spawn(async { 
        println!("inline async block");
        let val = yield_with_value(42).await;
        println!("inline async got: {}", val);
    });
    run();
}

pub struct Executor {
    pub tasks: Vec<Pin<Box<dyn Future<Output = ()> + Send + 'static>>>,
}

static mut EXECUTOR: Executor = Executor { tasks: Vec::new() };

fn spawn<F>(f: F)
where
    F: Future<Output = ()> + Send + 'static,
{
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(Box::pin(f));
}

fn pick_next_task() -> Option<Pin<Box<dyn Future<Output = ()> + Send + 'static>>> {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.pop()
}

fn put_prev_task(task: Pin<Box<dyn Future<Output = ()> + Send + 'static>>) {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(task)
}

async fn yield_with_value(value: i32) -> i32 {
    let mut flag = false;
    poll_fn(move |_cx| {
        if !flag {
            flag = true;
            Poll::Pending
        } else {
            Poll::Ready(value * 2)
        }
    })
    .await
}

async fn complex_async_operation() -> String {
    poll_fn(|_cx| {
        let result = String::from("async_result");
        Poll::Ready(result)
    })
    .await
}

async fn simple_delay() {
    let mut counter = 0;
    poll_fn(|_cx| {
        counter += 1;
        if counter < 2 {
            Poll::Pending
        } else {
            Poll::Ready(())
        }
    })
    .await;
}

fn run() {
    let waker = Waker::noop();
    let mut cx = Context::from_waker(&waker);
    loop {
        if let Some(mut task) = pick_next_task() {
            match task.as_mut().poll(&mut cx) {
                Poll::Pending => {
                    put_prev_task(task);
                }
                Poll::Ready(_) => {}
            }
        } else {
            break;
        }
    }
}

async fn test1() {
    println!("run test task 1 - before first await");
    let value1 = yield_with_value(10).await;
    println!("run test task 1 - got value {}, before second await", value1);
    let message = complex_async_operation().await;
    println!("run test task 1 - got message '{}', before third await", message);
    simple_delay().await;
    println!("run test task 1 done - after third await");
}

async fn test2() {
    println!("run test task 2 - before first await");
    let value = yield_with_value(5).await;
    println!("run test task 2 - got value {}, before second await", value);
    simple_delay().await;
    println!("run test task 2 done - after second await");
}

async fn test3() {
    println!("run test task 3 - before single await");
    let message = complex_async_operation().await;
    println!("run test task 3 done - got message '{}'", message);
} 
```
生成的 DWARF DIE 树里有这么一段
```
47ior8ew1d5rte53xrwz063lw
▸ namespace: core
▸ namespace: alloc
▸ base_type: u8
pointer_type: *const u8
base_type: usize
▾ namespace: future_executor_test
  ▾ namespace: complex_async_operation
    ▾ namespace: {async_fn#0}
      structure_type: {closure_env#0}
  ▾ namespace: simple_delay
    ▾ namespace: {async_fn#0}
      ▸ structure_type: {closure_env#0}
  ▾ namespace: yield_with_value
    ▾ namespace: {async_fn#0}
      ▸ structure_type: {closure_env#0}
      member: flag
      member: value
base_type: ()
pointer_type: &mut i32
base_type: i32
```

我从这段 DIE 树输出中推测：除了主要的异步函数状态机结构体（`{async_fn_env#0}`）之外，Rust编译器还会为异步函数内部使用的 `poll_fn` 创建额外的闭包环境结构（`{closure_env#0}`）。这些闭包环境位于 `namespace: {async_fn#0}` 内部，用于捕获闭包内的局部变量。例如在 `yield_with_value` 函数中，`{closure_env#0}` 结构包含了 `flag` 和 `value` 两个成员变量，这些是传递给 `poll_fn` 的 `move` 闭包捕获的变量。

这个发现解释了为什么有些异步函数的 DWARF 结构看起来更加复杂：
- `{async_fn_env#0}` 是主异步函数的状态机结构，包含所有 suspend 状态
- `{closure_env#0}` 是 `poll_fn` 等内部闭包的环境结构，包含闭包捕获的变量

注意这第三个例子节选出的 DIE 树输出也满足之前提到的“只有structure_type没有subprogram”的情况（在第三个例子中，`{async_fn#0}`是 namespace 不是 subprogram），所以我节选出来的这段 DIE 树输出也是“只展示了异步函数的上下文，没有展示异步函数本身”的情况。

简而言之，通过观察不同程序的 dwarf DIE 树，我有两个重要的发现：

第一个重大发现是，异步函数 `{async_fn#0}` 的兄弟节点就是我们要找的 future 结构体 `{async_fn_env#0}` 这样我们就有一个非常清晰的办法找到函数和future的对应关系了（见下文）

第二个发现是，这个输出找到了我们工具没能找到 `reqwest::get` 的原因：在 dwarf 中这个结构体就叫 `get`，GDB 在这个函数名前面加上`reqwest::`是为了和别的同名函数区分，但是 dwarf 已经有唯一的 offset 作为标识了，因此就不需要这种区分（正因为如此，我们生成的）。这个是 Rust 语言特有的问题，在官方文档中也有说明：



> Because GDB implements Rust name-lookup semantics in expressions, it will sometimes prepend the current crate to a name. For example, if GDB is stopped at a breakpoint in the crate ‘K’, then print ::x::y will try to find the symbol ‘K::x::y’. 

这让我想到了 GDB 的 `maint print objfile` 命令。这个命令能打印出 GDB 中符号名、添加了crate名字（比如`reqwest::`）的符号名和 DWARF 对应关系的索引：

```
    [59280] ((cooked_index_entry *) 0x7557d0177010)
    name:       {async_fn_env#0}<&str>
    canonical:  {async_fn_env#0}<&str>
    qualified:  reqwest::get::{async_fn_env#0}<&str>
    DWARF tag:  DW_TAG_structure_type
    flags:      0x2 [IS_STATIC]
    DIE offset: 0x6934a
    parent:     ((cooked_index_entry *) 0x7557d0176fe0) [get]

    [59281] ((cooked_index_entry *) 0x7557d01a25c0)
    name:       {async_fn_env#0}<&str>
    canonical:  {async_fn_env#0}<&str>
    qualified:  reqwest::get::{async_fn_env#0}<&str>
    DWARF tag:  DW_TAG_structure_type
    flags:      0x2 [IS_STATIC]
    DIE offset: 0xf6621
    parent:     ((cooked_index_entry *) 0x7557d01a2590) [get]

    [59282] ((cooked_index_entry *) 0x7557d00bf950)
    name:       {async_fn_env#0}<&str>
    canonical:  {async_fn_env#0}<&str>
    qualified:  reqwest::get::{async_fn_env#0}<&str>
    DWARF tag:  DW_TAG_structure_type
    flags:      0x2 [IS_STATIC]
    DIE offset: 0xc257
    parent:     ((cooked_index_entry *) 0x7557d00bf920) [get]
```

这个索引有个缺点就是过大了，一个简单的爬虫程序的索引列表花了20秒才生成。

回到 dwex 工具，这个工具的特色在于：将平铺展示的 DWARF 数据还原回了树状的。其他的工具（包括 [dwarf2json](https://github.com/volatilityfoundation/dwarf2json) [dwarf_dumper](https://github.com/DimitriFourny/dwarf_dumper) 等工具）都没有这个功能。我们的 parser 读取平铺的 DIE 然后利用找到的 member 属性构建了future的依赖树，但没有去分析 DIE 之间的层级关系。

如果我们的 parser 也有这种层级关系的话，就可以通过如下的 heuristic 解决 poll 函数和 future 之间对应关系的问题。

- 运行状态获取层
  - 获取 poll 函数
  - 解析出相关 future 结构体
  - 在相关 future 结构体的 poll 函数上插桩
  - 在每一个 thread 上，记录并缓存不同 task (最顶层 future) 的 backtrace

- dwarf 解析层
  - poll 函数名 -> future结构体:
    - 将 poll 函数名拆分成层级（其实可以用上面提到的 GDB 的索引，但是那个索引的生成速度太慢），比如说 `reqwest::get::{async_fn#0}<&str>` 拆分成 `reqwest` `get` 和 `{async_fn#0}<&str>`
      - 注意，一定要加上末尾的 `{async_fn#0}<&str>`，reqwest::get 可能是另一个函数或结构体！
    - 在每一个**编译单元**里按照拆分出的层级查找 poll 函数名（往往会查找到多个，因为在rust中一个crate是一个编译单元，而同一个函数会在不同crate里被调用）。比如在dwarf中的每一个编译单元“子树”中，先查找 `DW_TAG_namespace: reqwest` ，如果找到就查找它里面的 `DW_TAG_NAMESPACE: get`，再找 `DW_TAG_subprogram: {async_fn#0}<&str>`
    - 在每一个查找到的 poll 函数名（DW_TAG_subprogram）的同一层中可以找到这个异步函数对应的 future结构体（future结构体是我编的名字，是异步函数生成的闭包结构体和 实现了 Future trait的 结构体的统称）
  - future 结构体 -> poll 函数名
    - 如果提供的是 future 结构体的 dwarf偏移量，那么直接找到这个 future 结构体
    - 如果提供的是 future 结构体名字，将它拆分成层级，比如说 `reqwest::get::{async_fn_env#0}` 拆分成 `reqwest` `get` 和 `{async_fn_env#0}`
      - 注意，一定要加上 `{async_fn_env#0}`，reqwest::get 可能是另一个函数或结构体！
    - 在每一个**编译单元**里按照拆分出的层级查找 future 结构体名字（往往会查找到多个，因为在rust中一个crate是一个编译单元，而同一个future 结构体名字会在不同crate里被调用）。比如在dwarf中的每一个编译单元“子树”中，先查找 `DW_TAG_namespace: reqwest` ，如果找到就查找它里面的 `DW_TAG_NAMESPACE: get`，再找 `DW_TAG_structure_type: {async_fn_env#0}<&str>`
    - 在每一个查找到的 future结构体（DW_TAG_namespace）的同一层中可以找到这个异步函数对应的 poll 函数（**已验证：每个异步函数只有一个 {async_fn#0} 函数，编译器不会以 .await 标签为界将异步函数分割成若干个同步函数，而是在一个函数内部使用状态机实现不同的 suspend 状态**）
      - 验证方法：编写三个不一样且不会被优化的异步函数，在 future_executor_test/src/main.rs 的 test1 函数中分别 await ，然后用 dwarf 浏览器观察，发现 test1 namespace 下还是只有一个 `{async_fn#0}`，没有 `{async_fn#1}` 等.
        - 强调“三个不一样且不会被优化的异步函数“是因为，如果在 test1 函数中 await 同一个异步函数3次，那么可能（这个没有经过验证，只是自己的猜想中可能会出现的编译器行为）由于基于 .await 标签"拆分"（事实上没有拆分，这里只是假设如果有拆分的话）出来的函数的行为是一致的，编译器会把这几个"拆分"出来的函数合并成1个 {async_fn#?} 函数
  - 获取相关 future 结构体
    - 目前生成的 future 依赖关系已经足够用，如果将核心数据结构改用类似 dwex 的那种完整树状 DIE 的话会大大增加可维护性
      - 添加一个 future 结构体判断逻辑：和它同一层有 `DW_TAG_subprogram: {async_fn#0}`，这样可以减少基于 future 关键字进行过滤的功能带来的误判，甚至可以考虑把基于 future 关键字进行 future 结构体判断的代码删掉

为了做到上述改进，我们有三种方案：
1. 改进现有的dwarf.py（基于objdump输出）
2. 将 dwex（基于pyelftools） 中的 dwarf 解析代码里引用的 QT 方法/函数替换为我们自己的数据结构，从而将 dwex 代码移植到我们的代码库中
3. 提取 GDB 中 dwarf 解析模块，添加 future依赖关系解析和 DIE 层级关系解析功能

我决定采用方案2，因为有现成代码可以参考，工作量小一些。

首先拷贝 dwex 源代码到 dwarf/ 文件夹，然后删掉 QT 相关的内容。

看了下 dwex 源代码，只有一个 tree.py 是和我们的工作相关的，需要移植的，再加上一些其他源文件里的工具函数应该就可以了。

首先在 requirements.txt 中添加一下依赖：

```
filebytes>=0.10.1
pyelftools>=0.32
# pyobjc if platform.system() == 'Darwin', currently we don't care about macOS
```

然后安装这些依赖。

然后引入dwex源代码

然后可以开改了，幸运的是工作量并不大，只需要移除以下 QT 图形库相关的依赖：

```python
from bisect import bisect_left, bisect_right
from typing import Union
from PyQt6.QtCore import Qt, QAbstractItemModel, QModelIndex # remove
from PyQt6.QtWidgets import QApplication # remove

from elftools.dwarf.die import DIE
from elftools.dwarf.compileunit import CompileUnit

from .fx import bold_font, blue_brush # remove
from .dwarfutil import DIE_has_name, DIE_name, has_code_locati52on, safe_DIE_name, top_die_file_name
from .dwarfone import DIEV1
```

其他源文件先留着（因为后面可能还要提取出 DIE 显示成表格的功能），反正只要不 import 就不会报错。

然后编写 init_dwarf_analysis GDB 命令，这个命令会初始化 DIE 树. 命令本身不难实现，值得记录的反倒是以下两个 Python 运行环境的问题. 第一个问题是我们的包使用了 pyelftools 这个第三方包，那就意味着一定要用虚拟环境了（ubuntu24.04默认禁用全局python包），但是 GDB 里的 python 解释器找不到已经安装好的虚拟环境：

```
Python Exception <class 'ModuleNotFoundError'>: No module named 'elftools'
```

解决办法是，修改 Makefile，增加 PYTHONPATH 环境变量（虚拟环境本质上就是利用操作系统的软链接功能新增一个专属于本项目的 python 解释器和依赖文件目录）

```Makefile
test-gdb: build-tokio-test
    PYTHONPATH="venv/lib/python3.12/site-packages:$$PYTHONPATH" gdb -x src/main.py --args tests/tokio_test_project/target/debug/tokio_test_project
```

makefile 在这里派上用场了。

第二个问题是一个莫名其妙的类型错误：

```
Python Exception <class 'AttributeError'>: type object 'Callable' has no attribute '_abc_registry'
```

我都不知道 `_abc_registry` 是什么。

最后查明是因为我们用的是已经内置 typing 模块的 python3.12，但是根据 requirements.txt, 我们却安装了适用于 python3.5 的外部 typing 模块，于是`elftools`尝试 import 内置 typing 模块的时候却引入了老版本的外部 typing 模块，造成了这个问题。解决办法是在 requirements.txt 中删除外部 typing 模块并清空 venv 文件夹（我提供了 `make clean-venv` 命令）。

在移植了 `dwex` 的 DIE 树之后，我编写了上文提到的 DIE 树内的搜索算法（和一个测试脚本），这个算法写起来很别扭，因为一般的 DFS 算法搜索某个元素就好了，我们的这个 "DFS算法" 搜索的是一串元素，也就是说不仅节点本身要符合某个条件，这个节点的父亲节点，爷爷节点......也需要符合某些条件。需要注意的是，泛型不应当从函数名中被去除（因为可能出现带泛型和不带泛型的同名函数同时出现的情况），泛型内的`::`不应该作为分割符。

实际上如果不实现这个 DIE 树，而是直接把所有 DIE 的全名拼接出来（比如 `{async_fn#0} -> reqwest::get::{async_fn#0}`）然后直接搜索全名也是可行的，但是由于 DIE 太多了（一个用 tokio 下载单个网页的简单爬虫就有三百多个编译单元，每个编译单元内有 50-1000 个 DIE），这个列出 DIE 和拼接全名的过程会非常漫长，生成的 "DIE 列表" 文件也会非常巨大，因此只能需要用到某个 DIE 元素的时候再在 DIE 树里搜索。

**注意，目前只处理了 `函数{async_fn#?} <-> future结构体{async_fn_env#?}` 的情况，不过在现有的代码框架上添加其他的情况应该不是很困难。**

比如，我添加了 `_build_future_struct_name` 和 `_build_poll_function_name` 函数，可以用于处理将来可能出现的，DIE 树内搜索路径构建出来的名称和实际的名称不一致的情况。以及目前暂未处理的 `closure_env#` 和 `impl#` 的情况。

**想到一个问题，如何验证我们工具所跟踪出来信息（future依赖和异步backtrace）的完整性? 最方便的办法应该是和 runtime 内置的 tracer 进行比较（比如和 tokio-console）因为 runtime 内置的 tracer 展示的信息一般具有完整性** 这是后期的一个任务。

有了 poll->future 和 future->poll 的功能后，dwarf 解析层的任务就基本完成了，接下来需要编写处理运行状态获取层。

在此之前我需要修改以下 async_deps.json 的格式. 因为这个 json 里的内容是要被反复读取的（被用于搜索 future依赖）而它的格式其实会降低搜索效率。主要的问题是：

async 依赖树的每一项都是 "函数名<DIE offset>" 的格式，这个格式虽然保留了函数名便于阅读，又添加了唯一的 DIE offset 防止重名，但是每一次读取这种字符串都需要用正则表达式解析出 函数名和 DIE offset. 

最简单的解决方案是： 

1. async 依赖树只保留 DIE offset，这样 python 读取 json 之后可以直接把 DIE offset 当作 Dict 的 key 访问到某个元素的 future 依赖关系。这样做代码简单且高效。
2. async_functions 和 state_machines 中的每一项的 key 都改为 DIE offset。这么做的目的是：第一个解决手段导致 async 依赖树里只有 DIE offset 了，而**我们还是需要读取 future 名的（这里又又多出来一个工作，future 名和 DIE offset 转换变成了一个需要反复被用到的功能，而且和前面关于为什么不把 DIE 树直接拼接出全名然后全部打印的讨论一样， future-die_offset的索引文件会非常巨大且生成时间过长。因此需要将 future <-> DIE offset 的功能保留在内存里面随时准备被调用。所以 async_dependencies.py 不可以是一个终端命令了，要重新改成 GDB 内部的命令）** 这样需要读取每一个 DIE offset 对应的future名的时候就很方便     

在解决了这个问题后，我继续编写运行状态获取层。第一步 - 第四步的代码都应该实现在 StartAsyncDebugCommand 的 invoke 方法里（插在现有代码之前，插件加载代码要放在 invoke 方法的最后），第五和第六步应该要实现一个 runtime plugin（src/core/runtime_plugins 新建一个.py） （其中包含了存储插桩数据的数据结构的实现,还要保证这个数据结构能被 inspect-async 命令访问到），这个 runtime plugin 调用的插桩代码是一个单独的新 tracer（src/core/tracers 新建一个 .py）. 

第一步是读取 poll_map.json 中用户勾选的“感兴趣函数”，并且利用 pollToFuture 方法转换为 "感兴趣future"

第二步是，利用之前编写的 DIE 树和几个相关方法，实现查询 poll 和 future 的 DIE offset 的功能。查询功能的做法是，解耦之前的 pollToFuture 和 futureToPoll 方法，将每个方法分别拆分成 “在 DIE 树中找到 poll/future” 和 “在找到的 poll/future 附近找到 future/poll” 两个方法，这样的话我们修改一下 “在 DIE 树中找到 poll/future” 方法，就能让它们额外提供找到的 poll/future 的 DIE offset。 顺便我们也修改一下 “在找到的 poll/future 附近找到 future/poll” 方法，让它们也额外提供找到的 future/poll 的 DIE offset 供后续调用。这样做提高代码复用率，提升代码抽象层次，降低后续维护难度。 

第二步的实现步骤：1. 搜索源代码并给 pollToFuture 和 futureToPoll 方法添加一些 type annotation，从而知道有了 DIE 数据结构之后怎么获取 DIE offset. 2. 修改 pollToFuture 方法 3. 修改 futureToPoll 方法

第三步是读取 async_deps.json 中的 DIE 依赖关系，并且对“感兴趣 future”进行 "future 扩展". 往长辈方向"扩展"可以知道异步调用栈的底部和协程的划分（一个最底层的 future 就是一个协程），往子孙方向"扩展"可以知道异步调用栈的顶部。注意，在扩展的过程中不要使用 async_deps.json 内部的 DIE offset - 函数/结构体名 对照表（`offset_to_name`）那个对照表是从 objdump 的输出中提取出来的，所以函数名/结构体名不一定和 elftools 的解析结果一致，因此仅供 async_deps.py 内部使用。我们只能使用 DIE 树的数据结构和方法。具体代码实现我建议这么做：在 `StartAsyncDebugCommand` 类中，写一个 `offsetToDIE` 方法，参考 `src/core/dwarf/__main__.py`的 `on_byoffset` 方法，利用 DIE 树的现有 API 找到 DIE offset 对应的 DIE ，然后利用 `is_async_function_die` 和 `is_future_struct_die` 方法判断是哪个类型的 DIE，并返回 DIE + DIE 类型。

在实现第三步时会遇到一个困难，我们用来测试的 `reqwest::get::{async_fn#0}` 函数（对应 future `reqwest::get::{async_fn_env#0}` ）在 async_deps.json 中不显示全名，只显示最后一部分（`{async_fn#0}`、`{async_fn_env#0}`），而最后一部分偏偏是编译器生成的占位符，这些占位符只在当前命名空间下是唯一的，在当前命名空间以外会有非常多的重名. 因此我们需要改用 DIE offset 进行 future 依赖关系的查询。具体做法是在“第一步”后添加一个小步骤：把“感兴趣future”转换为 DIE offset 供第二步查询。特别需要注意的是 `Pin<&mut reqwest::get::{async_fn_env#0}<&str>>` 的 DIE 是 `Pin` 这个智能指针的 DIE，不是 `reqwest::get::{async_fn_env#0}` 的 DIE。 想获得 `reqwest::get::{async_fn_env#0}` 的 DIE 只能利用第二步的改写成果，获取`reqwest::get::{async_fn_env#0}`的 DIE offset，然后在 async_deps.json 里查询这 DIE offset。  

第四步是利用 pollToFuture 和 FutureToPoll 功能，获得扩展后的 future 列表对应的 poll 函数

第五步是利用之前编写的插桩框架对这些 poll 函数插桩。

第六步是利用之前编写的插桩框架获取异步调用栈信息。第一部分的工作是设计和编写用于给插桩代码存储数据的数据结构。该数据结构存储在一个 runtime plugin 里（放在 runtime_plugins 文件夹下的 runtime plugin），是一个多级字典`dict[process][thread][coroutine]`. 第二部分的工作是编写插桩代码本身（即放在tracers/文件夹里的一个tracer），插桩代码获取的数据有：进程id，线程id，协程id（通过我们之前的分析，future依赖树最顶层的那个future就等于一个协程）。函数进入时，和函数退出时都要运行这段插桩代码，这样做的目的是：函数退出时，调用栈也会对应地更新（调用栈里最顶层的函数调用被去除）

第七步是编写 inspect-async 命令，读取并显示第五步中存储的数据结构。

代码框架基本搭建完成，但是有两个问题：

0. ~~没有子节点~~（看了一下`reqwest.get`的源代码，发现这个函数中会自动生成一个新future（没有赋值到变量上）然后直接.await，换句话说这个函数里 await 的 future 是动态生成的，所以我们的 future 依赖搜索工具没有检测到 `reqwest.get` 的子 future. 这种情况现在可以先不管，等后面有时间了再解决）
1. 搜索不到这个 future 本身的 poll 函数
2. 明明找到2个长辈节点，却不去搜索它们的 poll 函数


```
(gdb) init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
Loading DWARF information from: tests/tokio_test_project/target/debug/tokio_test_project
Successfully initialized DWARF analysis for: tests/tokio_test_project/target/debug/tokio_test_project
Found 315 compilation units
You can now access the tree with: python tree = gdb.dwarf_tree
Or access DWARF info with: python info = gdb.dwarf_info
(gdb) start-async-debug 
[rust-future-tracing] Step 1: Reading user-selected interesting functions...
[rust-future-tracing] Found interesting poll function: static fn reqwest::get::{async_fn#0}<&str>(*mut core::task::wake::Context)
[rust-future-tracing] Mapped static fn reqwest::get::{async_fn#0}<&str>(*mut core::task::wake::Context) -> reqwest::get::{async_fn_env#0}<&str> (DIE offset: 93698)
[rust-future-tracing] Found 1 interesting futures:
  - reqwest::get::{async_fn_env#0}<&str>
[rust-future-tracing] === Step 3: Performing future expansion ===
[rust-future-tracing] Converting interesting futures to DIE offsets...
[rust-future-tracing] Converting future to DIE offset: reqwest::get::{async_fn_env#0}<&str>
[rust-future-tracing] Mapped reqwest::get::{async_fn_env#0}<&str> -> DIE offset: 49751
[rust-future-tracing] Expanding future dependencies...
[rust-future-tracing] Loaded async dependencies from /home/oslab/rust-future-tracing/results/async_deps.json
[rust-future-tracing] Expanding dependencies for DIE offset: 0xc257
[rust-future-tracing] Expansion complete:
  - Total expanded DIE offsets: 2
  - Coroutines (bottom-level): 1
  - Call stack tops: 2
[rust-future-tracing] Validating expanded futures with DIE tree...
[rust-future-tracing] Validation complete:
--Type <RET> for more, q to quit, c to continue without paging--c
  - Async functions: 0
  - Future structs: 1
  - Other DIEs: 1
  - Invalid offsets: 0
[rust-future-tracing] === Step 3 complete ===
[rust-future-tracing] Step 3 complete. Expanded to 2 total futures
[rust-future-tracing] === Step 4: Converting expanded futures to poll functions ===
[rust-future-tracing] Converting future to poll function: {async_fn_env#0}<&str> (offset: 49751)
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct at offset: 49751
[rust-future-tracing] WARNING: No poll function found for future: {async_fn_env#0}<&str>
[rust-future-tracing] Step 4 complete. Found 0 unique poll functions:
[rust-future-tracing] No poll functions found from expanded futures, cannot continue
(gdb) 
```

先解决问题1. 根据 log 我们发现我们在检索 `49751` 这个 DIE offset，然而我用 dwex 看了下这个 DIE offset，它是之前讨论过的只有 async_fn_env 没有 async_fn 的情况。因此我推测某处搜索 DIE 并返回 DIE offset 的代码有误. 很有可能是因为之前简单地只区各种搜索结果的第一个. 于是在源代码中搜索 `[0]` 得到如下结果：

```python
        for future_name in interesting_futures:
            print(f"[rust-future-tracing] Converting future to DIE offset: {future_name}")
            
            # Use our decomposed method from Step 2 to find the future struct DIE
            future_matches = self.find_future_struct_in_dwarf_tree(future_name)
            
            if future_matches:
                # Take the first match and get its offset
                future_die, future_offset = future_matches[0]
                die_offsets.append(future_offset)
                print(f"[rust-future-tracing] Mapped {future_name} -> DIE offset: {future_offset}")
            else:
                print(f"[rust-future-tracing] WARNING: Could not find DIE offset for future: {future_name}")
‵‵‵
我们要的 DIE 实际上是 future_matches[1,2,3,4.....] 中的一个 ，而 future_matches[0] 是我们之前提到的只有 async_fn_env 没有 async_fn 的情况。解决办法是对每个 future_match 做检验，使用第一个包含 async_fn 兄弟的 DIE 的 DIE offset.

修改后的代码：

```python
            if future_matches:
                future_offsets = []
                for die, offset in future_matches:
                    poll_function = self._find_sibling_poll_function(die)
                    if poll_function:
                        future_offsets.append(poll_function.offset)
                if not future_offsets:
                    print(f"[rust-future-tracing] WARNING: No poll function found for future: {future_name}")
                    continue
                # Return the first found offset as the representative DIE offset, report others if any
                future_offset = future_offsets[0]
                if len(future_offsets) > 1:
                    print(f"[rust-future-tracing] Warning: Multiple poll functions found for future {future_name}, the following are ignored:")
                    for offset in future_offsets[1:]:
                        print(f"  - DIE offset: {offset}")
                # Append the first found offset to the list
                die_offsets.append(future_offset)
                print(f"[rust-future-tracing] Mapped {future_name} -> DIE offset: {future_offset}")
            else:
                print(f"[rust-future-tracing] WARNING: Could not find DIE offset for future: {future_name}")
```
蚌埠住了，刚才写错了， poll_function 变量的值本身是没用的，我们要用的是 DIE 本身的 offset 而不是 poll 函数的 offset


```python
            if future_matches:
                future_offsets = []
                for die, offset in future_matches:
                    poll_function = self._find_sibling_poll_function(die)
                    if poll_function:
                        future_offsets.append(offset)
                if not future_offsets:
                    print(f"[rust-future-tracing] WARNING: No poll function found for future: {future_name}")
                    continue
                # Return the first found offset as the representative DIE offset, report others if any
                future_offset = future_offsets[0]
                if len(future_offsets) > 1:
                    print(f"[rust-future-tracing] Warning: Multiple poll functions found for future {future_name}, the following are ignored:")
                    for offset in future_offsets[1:]:
                        print(f"  - DIE offset: {offset}")
                # Append the first found offset to the list
                die_offsets.append(future_offset)
                print(f"[rust-future-tracing] Mapped {future_name} -> DIE offset: {future_offset}")
            else:
                print(f"[rust-future-tracing] WARNING: Could not find DIE offset for future: {future_name}")
        
        return die_offsets

```

搜索`[0]`时找到另外两个取搜索结果的第一个的代码，在终端中报告忽略掉的搜索结果，以便后续改进：

```python
        # Return the full name of the first future struct found, return others if any
        if len(future_structs) > 1:
            print(f"[rust-future-tracing] Warning: Multiple future structs found for poll function {poll_fn_name}, the following are ignored:")
            for future_die, future_offset in future_structs[1:]:
                print(f"  - {safe_DIE_name(future_die, '')} (DIE offset: {future_offset})")
        # Use the first match as the primary result
        future_die, future_offset = future_structs[0]
        future_name = self._build_future_struct_name(future_die, poll_fn_name)
        print(f"[rust-future-tracing] Mapped {poll_fn_name} -> {future_name} (DIE offset: {future_offset})")
        return future_name
```

```python
        # Return the first poll function found, report others if any
        if len(poll_functions) > 1:
            print(f"[rust-future-tracing] Warning: Multiple poll functions found for future struct {future_struct_name}, the following are ignored:")
            for poll_die, poll_offset in poll_functions[1:]:
                print(f"  - {safe_DIE_name(poll_die, '')} (DIE offset: {poll_offset})")
        # Use the first match as the primary result
        poll_die, poll_offset = poll_functions[0]
        poll_name = self._build_poll_function_name(poll_die, future_struct_name)
        print(f"[rust-future-tracing] Mapped {future_struct_name} -> {poll_name} (DIE offset: {poll_offset})")
        return poll_name
```

问题 1 解决了。问题2暂时无法验证是否仍会出现，因为问题1解决后，本工具报告的结果是 `reqwest.get` 没有长辈节点. 后面我会写一个新的测例来验证是否仍会出现这个问题。

插桩代码似乎没有还原函数名：

```
oslab@oslab-VMware-Virtual-Platform:~/rust-future-tracing$ make test-gdb
GNU gdb (Ubuntu 15.0.50.20240403-0ubuntu1) 15.0.50.20240403-git
Copyright (C) 2024 Free Software Foundation, Inc.
License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
Type "show copying" and "show warranty" for details.
This GDB was configured as "x86_64-linux-gnu".
Type "show configuration" for configuration details.
For bug reporting instructions, please see:
<https://www.gnu.org/software/gdb/bugs/>.
Find the GDB manual and other documentation resources online at:
    <http://www.gnu.org/software/gdb/documentation/>.

For help, type "help".
Type "apropos word" to search for commands related to "word"...
Reading symbols from tests/tokio_test_project/target/debug/tokio_test_project...
warning: Missing auto-load script at offset 0 in section .debug_gdb_scripts
of file /home/oslab/rust-future-tracing/tests/tokio_test_project/target/debug/tokio_test_project.
Use `info auto-load python-scripts [REGEXP]' to list them.
[rust-future-tracing] Loaded runtime plugin: tokio (currently does nothing)
(gdb) init-dwarf-analysis tests/tokio_test_project/target/debug/tokio_test_project
Loading DWARF information from: tests/tokio_test_project/target/debug/tokio_test_project
Successfully initialized DWARF analysis for: tests/tokio_test_project/target/debug/tokio_test_project
Found 315 compilation units
You can now access the tree with: python tree = gdb.dwarf_tree
Or access DWARF info with: python info = gdb.dwarf_info
(gdb) start-async-debug 
[rust-future-tracing] Step 1: Reading user-selected interesting functions...
[rust-future-tracing] Found interesting poll function: static fn reqwest::get::{async_fn#0}<&str>(*mut core::task::wake::Context)
[rust-future-tracing] Mapped static fn reqwest::get::{async_fn#0}<&str>(*mut core::task::wake::Context) -> reqwest::get::{async_fn_env#0}<&str> (DIE offset: 93698)
[rust-future-tracing] Found 1 interesting futures:
  - reqwest::get::{async_fn_env#0}<&str>
[rust-future-tracing] === Step 3: Performing future expansion ===
[rust-future-tracing] Converting interesting futures to DIE offsets...
[rust-future-tracing] Converting future to DIE offset: reqwest::get::{async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
--Type <RET> for more, q to quit, c to continue without paging--c
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] No poll function found for future struct: {async_fn_env#0}<&str>
[rust-future-tracing] Mapped reqwest::get::{async_fn_env#0}<&str> -> DIE offset: 93698
[rust-future-tracing] Expanding future dependencies...
[rust-future-tracing] Loaded async dependencies from /home/oslab/rust-future-tracing/results/async_deps.json
[rust-future-tracing] Expanding dependencies for DIE offset: 0x16e02
[rust-future-tracing] Expansion complete:
  - Total expanded DIE offsets: 1
  - Coroutines (bottom-level): 1
  - Call stack tops: 1
[rust-future-tracing] Validating expanded futures with DIE tree...
[rust-future-tracing] Validation complete:
  - Async functions: 0
  - Future structs: 1
  - Other DIEs: 0
  - Invalid offsets: 0
[rust-future-tracing] === Step 3 complete ===
[rust-future-tracing] Step 3 complete. Expanded to 1 total futures
[rust-future-tracing] === Step 4: Converting expanded futures to poll functions ===
[rust-future-tracing] Converting future to poll function: {async_fn_env#0}<&str> (offset: 93698)
[rust-future-tracing] Mapped future -> poll: {async_fn_env#0}<&str> -> {async_fn#0}<&str> (DIE offset: 93436)
[rust-future-tracing] Step 4 complete. Found 1 unique poll functions:
  1. {async_fn#0}<&str>
[rust-future-tracing] Step 4 complete. Ready to instrument 1 poll functions
[rust-future-tracing] Initialized AsyncBacktracePlugin for 1 poll functions.
[rust-future-tracing] === Step 5: Setting up instrumentation for poll functions ===
  - Will instrument: {async_fn#0}<&str>
[rust-future-tracing] === Step 5 complete ===
Function "{async_fn#0}<&str>" not defined.
[rust-future-tracing] All steps complete. Instrumentation is active.
Hint: Use 'continue' or 'run' to start the program, then 'inspect-async' to see results.
(gdb) 
```

排查结果：（目前代码库的）Step 4 中存了应该插桩的函数列表，然后 Step 5 读取了这个列表，所以是 Step 4 中调用 convert_expanded_futures_to_poll_functions 方法的问题. 在这个方法中，我调用了 _build_poll_function_name 方法两次，其中有这么个逻辑：



```python
        if len(hierarchy) >= 2:
            # Replace the last component ({async_fn_env#0}) with the poll function name
            namespace_parts = hierarchy[:-1]  # Everything except the last part
            
            # Build the full poll function name
            full_name = "::".join(namespace_parts) + "::" + poll_name
            return full_name
        else:
            # If the hierarchy is too short, just return the poll name
            # This can happen if the future struct name was not fully qualified
            print(f"[rust-future-tracing] Warning: Hierarchy too short for future struct: {future_struct_name}")
        
        return poll_name
```

~~其中 else 部分是我刚刚加上去的，也打印出来了. 所以把 `if len(hierarchy) >= 2:` 删掉就好了.~~ `if len(hierarchy) >= 2:` 是正确的，因为如果这个条件不满足的话 hierarchy 列表里只有一个或0个元素

删掉之后还是不对，发现这个函数的参数 future_struct_name 应该是完整的名字（比如`reqwest::get::{async_fn_env#0}`而不是`{async_fn_env#0}`）但所我们却把简略版名字（只包含最后一部分）传入进去了. 因此这个地方是不适合使用 _build_poll_function_name 的，我们要另外写一个 dieToFullName 方法:


```python

            if poll_result:
                poll_die, poll_offset = poll_result

                # poll_name = self._build_poll_function_name(poll_die, future_name)
                poll_name = self.dieToFullName(poll_die)
                if not poll_name:
                    print(f"[rust-future-tracing] WARNING: Could not build poll function name for future: {future_name}")
                    continue

```

```python

    def dieToFullName(self, die: DIE) -> str:
        """
        Convert a DIE to its full name, including namespace.
        
        Args:
            die (DIE type): The DIE object to convert
            
        Returns:
            str: Full name of the DIE with namespace
        """
        if not die:
            return ""
        
        # Get the name of the current DIE
        current_name = safe_DIE_name(die, "")
        if not current_name:
            return ""
        
        # Build the full name by traversing up the parent hierarchy
        name_parts = []
        current_die = die
        
        while current_die:
            current_die_name = safe_DIE_name(current_die, "")
            if current_die_name:
                # Only include meaningful names (skip empty names and compilation unit names)
                current_tag = current_die.tag if hasattr(current_die, 'tag') else ""
                
                # Skip compilation unit names as they're usually file paths
                if current_tag != 'DW_TAG_compile_unit':
                    name_parts.append(current_die_name)
            
            # Move to parent DIE
            if hasattr(current_die, '_parent') and current_die._parent:
                current_die = current_die._parent
            else:
                break
        
        # Reverse the list since we built it from child to parent
        name_parts.reverse()
        
        # Join with "::" to create the full qualified name
        if name_parts:
            return "::".join(name_parts)
        else:
            return current_name


```

至此这个错误修复完毕了，我们遇到了插桩阶段的新错误：


```python
[New Thread 0x7ffff65f86c0 (LWP 22045)]
[ThreadId(1)] Main async block START
[ThreadId(1)] Loop iteration START for URL: https://config.net.cn/tools/ProvinceCityCountry.html
[ThreadId(1)] INFO start to add a spider on: https://config.net.cn/tools/ProvinceCityCountry.html
[ThreadId(1)] before reqwest::get time: SystemTime { tv_sec: 1754322615, tv_nsec: 152539030 }
[ThreadId(1)] PRE-AWAIT reqwest::get for URL: https://config.net.cn/tools/ProvinceCityCountry.html
[New Thread 0x7ffff63f76c0 (LWP 22046)]
warning: could not find '.gnu_debugaltlink' file for /lib/x86_64-linux-gnu/libnss_mdns4_minimal.so.2

Thread 1 "tokio_test_proj" hit Temporary breakpoint -11, reqwest::get::{async_fn#0}<&str> ()
    at /home/oslab/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/reqwest-0.12.22/src/lib.rs:323
323     pub async fn get<T: IntoUrl>(url: T) -> crate::Result<Response> {
Python Exception <class 'NameError'>: name 'bp_commands' is not defined
Error occurred in Python: name 'bp_commands' is not defined
(gdb) 
```

造成这个错误的原因是，本工具执行的入口是 `src/main.py`，但是 bp_commands 是定义在 `src/__init__.py` 里的，然而 GDB 的 `python python_statements` 命令只能访问 `src/main.py` 的全局命名空间，（默认处于全局命名空间内）访问不到处于 `src/__init__.py` 命名空间的 `bp_commands`. 解决办法是将 `bp_commands` 和 `run_tracers` 函数显式地添加到 GDB 的全局命名空间 `__main__` 中，这样插桩框架就能够访问到这些变量和函数了。

具体的修改是在 `src/core/__init__.py` 中添加：

```python
# Make bp_commands available in GDB's global namespace
import __main__
__main__.bp_commands = bp_commands

# Make run_tracers available in GDB's global namespace since it's called by the instrumentation framework
__main__.run_tracers = run_tracers
```

这样修改后，当插桩框架执行 `python bp_commands[{cmd_index}]()` 命令时，就能在全局命名空间中找到 `bp_commands` 列表了。`run_tracers`也需要添加到全局命名空间中，因为插桩框架会通过调用这个函数来执行插桩代码.

此外，我把各个命令的初始化语句（比如 `StartAsyncDebugCommand()`）和它们的定义放到同一个文件内，main.py 里面 import 这些文件的时候会自动执行命令类的定义语句和初始化语句，这样更符合 GDB Python 项目的惯例.

下一步工作：
1. 编写 benchmark 测试我们这个方法的准确性
  - （比如可以跟 tokio-console / 
  - bugstalker 
  - 或自己在异步代码里添加一个宏
  - 进行对比，看看是否有跟踪到
    - 所有的协程和
    - 所有的 future 依赖关系）
2. 编写一个例子，里面包含所有异步代码的形式（比如 async fn, impl future 等，应该不止这两个但是我暂时不了解），看我们这个工具是否能跟踪所有的形式，如果不行的话需要修改代码。基于目前这个代码框架，修改起来不会太难


