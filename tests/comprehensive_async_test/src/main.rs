use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;
use async_trait::async_trait;

// 1. 标准的 async fn 函数
async fn standard_async_fn() -> i32 {
    tokio::time::sleep(Duration::from_millis(10)).await;
    42
}

// 2. 异步块
fn async_block() -> impl Future<Output = i32> {
    async {
        tokio::time::sleep(Duration::from_millis(10)).await;
        100
    }
}

// 3. 手动实现 Future trait
struct ManualFuture {
    counter: i32,
}

impl Future for ManualFuture {
    type Output = i32;

    fn poll(mut self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> {
        if self.counter > 0 {
            self.counter -= 1;
            Poll::Pending
        } else {
            Poll::Ready(42)
        }
    }
}

fn manual_future() -> ManualFuture {
    ManualFuture { counter: 3 }
}

// 4. 通过 Box 包装的 Future
fn boxed_future() -> Pin<Box<dyn Future<Output = i32>>> {
    Box::pin(async {
        tokio::time::sleep(Duration::from_millis(10)).await;
        200
    })
}

// 5. 使用 async-trait 的 trait
#[async_trait]
trait AsyncTrait {
    async fn async_method(&self) -> i32;
}

struct TraitImpl;

#[async_trait]
impl AsyncTrait for TraitImpl {
    async fn async_method(&self) -> i32 {
        tokio::time::sleep(Duration::from_millis(10)).await;
        300
    }
}

// 6. 泛型 async fn
async fn generic_async_fn<T>(value: T) -> T {
    tokio::time::sleep(Duration::from_millis(10)).await;
    value
}

// 7. 带生命周期的 async fn
async fn lifetime_async_fn(s: &str) -> String {
    tokio::time::sleep(Duration::from_millis(10)).await;
    s.to_string()
}

// 8. 在 impl 块中的 async fn
struct MyStruct;

impl MyStruct {
    async fn impl_async_fn(&self) -> i32 {
        tokio::time::sleep(Duration::from_millis(10)).await;
        500
    }
}

// 9. 使用 futures crate 的 combinators (修正版本)
use futures::future::{self, Either};
async fn combinators_async_fn() -> i32 {
    let f1 = Box::pin(async { 1 });
    let f2 = Box::pin(async { 2 });
    
    match future::select(f1, f2).await {
        Either::Left((v, _)) => v,
        Either::Right((v, _)) => v,
    }
}

// 10. 嵌套的异步函数调用
async fn nested_async_fn() -> i32 {
    let val1 = standard_async_fn().await;
    let val2 = async_block().await;
    val1 + val2
}

// 主函数，调用所有测试用例
#[tokio::main]
async fn main() {
    println!("开始测试各种异步实现方式");

    // 1. 标准 async fn
    let result1 = standard_async_fn().await;
    println!("standard_async_fn result: {}", result1);

    // 2. 异步块
    let result2 = async_block().await;
    println!("async_block result: {}", result2);

    // 3. 手动实现的 Future
    // let result3 = manual_future().await;
    // println!("manual_future result: {}", result3);

    // 4. Boxed Future
    let result4 = boxed_future().await;
    println!("boxed_future result: {}", result4);

    // 5. async-trait
    let trait_impl = TraitImpl;
    let result5 = trait_impl.async_method().await;
    println!("async_trait result: {}", result5);

    // 6. 泛型 async fn
    let result6 = generic_async_fn(600).await;
    println!("generic_async_fn result: {}", result6);

    // 7. 带生命周期的 async fn
    let result7 = lifetime_async_fn("hello").await;
    println!("lifetime_async_fn result: {}", result7);

    // 8. impl 块中的 async fn
    let my_struct = MyStruct;
    let result8 = my_struct.impl_async_fn().await;
    println!("impl_async_fn result: {}", result8);

    // 9. Combinators
    let result9 = combinators_async_fn().await;
    println!("combinators_async_fn result: {}", result9);

    // 10. 嵌套异步函数
    let result10 = nested_async_fn().await;
    println!("nested_async_fn result: {}", result10);

    println!("所有测试完成");
}
