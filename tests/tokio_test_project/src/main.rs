// mod sync_helpers {
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
//}

async fn async_function_one(base_url: &str) -> Result<String, reqwest::Error> {
    log_stage("async_function_one:start");

    simulate_cpu_work("async_function_one:cpu");

    let derived_url = next_url(base_url);

    log_stage("async_function_one:handoff_to_two");
    let text = async_function_two(derived_url).await?;
    log_stage("async_function_one:end");
    Ok(text)
}

async fn async_function_two(url: String) -> Result<String, reqwest::Error> {
    log_stage("async_function_two:start");

    jitter_delay();

    simulate_cpu_work("async_function_two:cpu");

    let decorated_url = append_stage_marker(&url);

    log_stage("async_function_two:handoff_to_three");
    let text = async_function_three(decorated_url).await?;
    log_stage("async_function_two:end");
    Ok(text)
}

async fn async_function_three(url: String) -> Result<String, reqwest::Error> {
    log_stage("async_function_three:start");

    jitter_delay();

    simulate_cpu_work("async_function_three:cpu");

    let response = reqwest::get(&url).await?;
    let body = response.text().await?;

    report_body_length(body.len());

    log_stage("async_function_three:end");
    Ok(body)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    log_stage("main:start");

    let base_url = "https://config.net.cn/tools/ProvinceCityCountry.html";
    let body = async_function_one(base_url).await?;
    report_body_length(body.len());

    log_stage("main:end");
    Ok(())
}