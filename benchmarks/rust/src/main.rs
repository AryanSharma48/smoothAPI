use serde::Serialize;
use smooth_api_core::{
    calculate_backoff, evaluate_response, BackoffConfig, JitterStrategy, RetryDecision,
};
use std::env;
use std::hint::black_box;
use std::time::Instant;

#[derive(Serialize)]
struct BenchmarkResult {
    workload: String,
    language: String,
    round: u32,
    iterations: u64,
    elapsed_ms: f64,
    ops_per_sec: f64,
    ns_per_op: f64,
}

fn verify_correctness(config: &BackoffConfig) {
    // 1. Backoff calculation checks
    let expected_backoffs = [(0, 100), (1, 200), (2, 400), (3, 800), (10, 30000)];
    for (attempt, expected) in expected_backoffs {
        let delay = calculate_backoff(attempt, config, None, 0.0);
        assert_eq!(
            delay, expected,
            "Rust correctness failed for backoff attempt {}",
            attempt
        );
    }

    // 2. Policy evaluation checks
    let d1 = evaluate_response(200, 0, config, None, None, 0.0);
    assert_eq!(d1, RetryDecision::Success);

    let d2 = evaluate_response(404, 0, config, None, None, 0.0);
    assert_eq!(d2, RetryDecision::Terminal);

    let d3 = evaluate_response(503, 0, config, None, None, 0.0);
    assert_eq!(d3, RetryDecision::Retry { delay_ms: 100 });

    let d4 = evaluate_response(429, 0, config, Some("5"), None, 0.0);
    assert_eq!(d4, RetryDecision::Retry { delay_ms: 5000 });

    let d5 = evaluate_response(500, 3, config, None, None, 0.0);
    assert_eq!(d5, RetryDecision::Exhausted);
}

fn bench_backoff(iterations: u64, warmup: u64, round: u32, config: &BackoffConfig) -> BenchmarkResult {
    let attempts = [0, 1, 2, 3, 10];
    let num_attempts = attempts.len();

    // Warm-up
    for i in 0..warmup {
        let att = attempts[(i as usize) % num_attempts];
        black_box(calculate_backoff(black_box(att), config, None, 0.0));
    }

    // Timed execution
    let start = Instant::now();
    for i in 0..iterations {
        let att = attempts[(i as usize) % num_attempts];
        black_box(calculate_backoff(black_box(att), config, None, 0.0));
    }
    let elapsed = start.elapsed();
    let elapsed_ms = elapsed.as_secs_f64() * 1000.0;
    let ops_per_sec = (iterations as f64) / elapsed.as_secs_f64();
    let ns_per_op = (elapsed.as_nanos() as f64) / (iterations as f64);

    BenchmarkResult {
        workload: "backoff_deterministic".to_string(),
        language: "rust".to_string(),
        round,
        iterations,
        elapsed_ms,
        ops_per_sec,
        ns_per_op,
    }
}

fn bench_policy(iterations: u64, warmup: u64, round: u32, config: &BackoffConfig) -> BenchmarkResult {
    let test_cases = [
        (200u16, 0u32, None),
        (404, 0, None),
        (503, 0, None),
        (429, 0, Some("5")),
        (500, 3, None),
    ];
    let num_cases = test_cases.len();

    // Warm-up
    for i in 0..warmup {
        let (status, attempt, header) = test_cases[(i as usize) % num_cases];
        black_box(evaluate_response(
            black_box(status),
            black_box(attempt),
            config,
            header,
            None,
            0.0,
        ));
    }

    // Timed execution
    let start = Instant::now();
    for i in 0..iterations {
        let (status, attempt, header) = test_cases[(i as usize) % num_cases];
        black_box(evaluate_response(
            black_box(status),
            black_box(attempt),
            config,
            header,
            None,
            0.0,
        ));
    }
    let elapsed = start.elapsed();
    let elapsed_ms = elapsed.as_secs_f64() * 1000.0;
    let ops_per_sec = (iterations as f64) / elapsed.as_secs_f64();
    let ns_per_op = (elapsed.as_nanos() as f64) / (iterations as f64);

    BenchmarkResult {
        workload: "retry_policy_evaluation".to_string(),
        language: "rust".to_string(),
        round,
        iterations,
        elapsed_ms,
        ops_per_sec,
        ns_per_op,
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let mut workload = "backoff_deterministic".to_string();
    let mut iterations = 100_000u64;
    let mut warmup = 10_000u64;
    let mut round = 1u32;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--workload" => {
                workload = args[i + 1].clone();
                i += 2;
            }
            "--iterations" => {
                iterations = args[i + 1].parse().unwrap_or(100_000);
                i += 2;
            }
            "--warmup" => {
                warmup = args[i + 1].parse().unwrap_or(10_000);
                i += 2;
            }
            "--round" => {
                round = args[i + 1].parse().unwrap_or(1);
                i += 2;
            }
            _ => {
                i += 1;
            }
        }
    }

    let config = BackoffConfig {
        base_delay_ms: 100,
        max_delay_ms: 30000,
        max_retries: 3,
        jitter: JitterStrategy::None,
    };

    // Pre-flight correctness check
    verify_correctness(&config);

    let result = match workload.as_str() {
        "backoff_deterministic" => bench_backoff(iterations, warmup, round, &config),
        "retry_policy_evaluation" => bench_policy(iterations, warmup, round, &config),
        other => {
            eprintln!("Unknown workload: {}", other);
            std::process::exit(1);
        }
    };

    println!("{}", serde_json::to_string(&result).unwrap());
}
