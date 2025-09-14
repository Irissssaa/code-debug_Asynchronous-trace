use async_std::io::{BufReader, WriteExt};
use async_std::net::{TcpListener, TcpStream};
use async_std::task;
// FIX 1: Replaced futures::prelude with async_std::prelude to avoid trait conflicts.
use async_std::prelude::*; 
use log::{info, warn};
use std::time::Duration;

/// 辅助异步函数：处理消息并回显
/// 它的存在是为了构建更深的逻辑调用栈
// FIX 2: The first argument is now explicitly the "writer" half of the stream.
async fn process_and_echo(writer: &mut TcpStream, msg: &str) -> async_std::io::Result<()> {
    info!("    -> Processing message: '{}'", msg.trim());
    // 模拟一个耗时的异步处理过程
    task::sleep(Duration::from_millis(150)).await;

    let response = msg.trim().to_uppercase();
    info!("    <- Responding with: '{}'", response);

    // 将处理后的消息写回客户端
    // Now that the prelude is fixed, these calls are unambiguous.
    writer.write_all(response.as_bytes()).await?;
    writer.write_all(b"\n").await?;
    Ok(())
}

/// 为每一个客户端连接创建一个独立的异步任务
async fn handle_connection(stream: TcpStream) {
    let peer_addr = stream.peer_addr().unwrap();
    info!("[CONN_HANDLER] Accepted connection from: {}", peer_addr);

    // FIX 3: Split the stream into a reader and a writer.
    // The original `stream` will be used for reading via `BufReader`.
    // The cloned `writer` will be used for writing.
    let reader = BufReader::new(&stream);
    let mut writer = stream.clone(); 
    
    let mut lines = reader.lines();

    while let Some(line_result) = lines.next().await {
        match line_result {
            Ok(line) => {
                if line.is_empty() {
                    break;
                }
                // FIX 4: Pass the mutable `writer` to the helper function.
                // This no longer conflicts with the `reader`'s borrow of the original `stream`.
                if let Err(e) = process_and_echo(&mut writer, &line).await {
                    warn!("[CONN_HANDLER] Error processing line: {}", e);
                    break;
                }
            }
            Err(e) => {
                warn!("[CONN_HANDLER] Error reading line: {}", e);
                break;
            }
        }
    }
    info!("[CONN_HANDLER] Connection from {} closed.", peer_addr);
}

/// 一个独立的顶级任务，用于打印心跳信息
async fn heartbeat_task() {
    loop {
        info!("[HEARTBEAT] System is alive...");
        task::sleep(Duration::from_secs(10)).await;
    }
}

#[async_std::main]
async fn main() {
    env_logger::builder()
        .filter_level(log::LevelFilter::Info)
        .format_timestamp_nanos()
        .init();

    // 启动心跳任务
    task::spawn(heartbeat_task());

    // 绑定到本地地址 8080 端口
    let listener = TcpListener::bind("127.0.0.1:8080").await.unwrap();
    info!("[MAIN] Listening on {}", listener.local_addr().unwrap());

    // 监听并接受新的TCP连接
    let mut incoming = listener.incoming();
    while let Some(stream_result) = incoming.next().await {
        match stream_result {
            Ok(stream) => {
                // 对于每一个新的连接，动态生成一个新的异步任务去处理它
                info!("[MAIN] Spawning new handler for incoming connection...");
                task::spawn(handle_connection(stream));
            }
            Err(e) => {
                warn!("[MAIN] Failed to accept connection: {}", e);
            }
        }
    }
}
