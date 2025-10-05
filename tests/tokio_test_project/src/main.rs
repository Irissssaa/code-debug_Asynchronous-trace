mod sync_helpers {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::thread;
    use std::time::{Duration, Instant};

    static REQUEST_COUNTER: AtomicUsize = AtomicUsize::new(0);

    pub fn log_stage(message: &str) {
        println!("[SYNC][{:?}] {message}", thread::current().id());
    }

    pub fn next_url(base: &str) -> String {
        let run_id = REQUEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        format!("{base}?run_id={run_id}")
    }

    pub fn append_stage_marker(url: &str) -> String {
        if url.contains('?') {
            format!("{url}&stage=two")
        } else {
            format!("{url}?stage=two")
        }
    }

    pub fn simulate_cpu_work(label: &str) {
        let start = Instant::now();
        while start.elapsed().as_micros() < 500 {
            std::hint::spin_loop();
        }
        println!("[SYNC] Simulated CPU work for {label}");
    }

    pub fn jitter_delay() {
        thread::sleep(Duration::from_millis(25));
    }

    pub fn report_body_length(len: usize) {
        println!("[SYNC] Response body length: {len} bytes");
    }
}

async fn async_function_one(base_url: &str) -> Result<String, reqwest::Error> {
    let log: fn(&str) = sync_helpers::log_stage;
    log("async_function_one:start");

    let cpu: fn(&str) = sync_helpers::simulate_cpu_work;
    cpu("async_function_one:cpu");

    let builder: fn(&str) -> String = sync_helpers::next_url;
    let derived_url = builder(base_url);

    log("async_function_one:handoff_to_two");
    let text = async_function_two(derived_url).await?;
    log("async_function_one:end");
    Ok(text)
}

async fn async_function_two(url: String) -> Result<String, reqwest::Error> {
    let log: fn(&str) = sync_helpers::log_stage;
    log("async_function_two:start");

    let pause: fn() = sync_helpers::jitter_delay;
    pause();

    let cpu: fn(&str) = sync_helpers::simulate_cpu_work;
    cpu("async_function_two:cpu");

    let decorator: fn(&str) -> String = sync_helpers::append_stage_marker;
    let decorated_url = decorator(&url);

    log("async_function_two:handoff_to_three");
    let text = async_function_three(decorated_url).await?;
    log("async_function_two:end");
    Ok(text)
}

async fn async_function_three(url: String) -> Result<String, reqwest::Error> {
    let log: fn(&str) = sync_helpers::log_stage;
    log("async_function_three:start");

    let pause: fn() = sync_helpers::jitter_delay;
    pause();

    let cpu: fn(&str) = sync_helpers::simulate_cpu_work;
    cpu("async_function_three:cpu");

    let response = reqwest::get(&url).await?;
    let body = response.text().await?;

    let reporter: fn(usize) = sync_helpers::report_body_length;
    reporter(body.len());

    log("async_function_three:end");
    Ok(body)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let log: fn(&str) = sync_helpers::log_stage;
    log("main:start");

    let base_url = "https://config.net.cn/tools/ProvinceCityCountry.html";
    let body = async_function_one(base_url).await?;

    let reporter: fn(usize) = sync_helpers::report_body_length;
    reporter(body.len());

    log("main:end");
    Ok(())
}