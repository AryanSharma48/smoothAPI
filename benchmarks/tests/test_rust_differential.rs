//! Differential runner: Direct Rust (smooth-api-core).
//!
//! Executes the canonical vectors in `benchmarks/config/differential_vectors.json`
//! against the shared Rust core and prints raw observations as JSON on stdout.
//! It performs no pass/fail judgement; scoring is done by `scripts/run_differential.py`.

use serde_json::{Map, Value, json};
use smooth_api_core::{
    BackoffConfig, CircuitBreaker, CircuitState, JitterStrategy, RetryDecision, calculate_backoff,
    evaluate_response,
};
use std::{env, fs};

fn parse_u64(v: &Value) -> Result<u64, String> {
    v.as_str()
        .ok_or_else(|| "expected decimal string".to_string())?
        .parse::<u64>()
        .map_err(|e| format!("u64 parse error: {e}"))
}

fn state_name(s: CircuitState) -> &'static str {
    match s {
        CircuitState::Closed => "CLOSED",
        CircuitState::Open => "OPEN",
        CircuitState::HalfOpen => "HALF_OPEN",
    }
}

fn run_backoff(vectors: &[Value]) -> Map<String, Value> {
    let mut out = Map::new();
    for v in vectors {
        let id = v["id"].as_str().unwrap().to_string();
        let result = (|| -> Result<Value, String> {
            let config = BackoffConfig {
                base_delay_ms: parse_u64(&v["base_delay_ms"])?,
                max_delay_ms: parse_u64(&v["max_delay_ms"])?,
                max_retries: 3,
                jitter: JitterStrategy::None,
            };
            let attempt = v["attempt"].as_u64().ok_or("attempt not u64")? as u32;
            Ok(json!({ "value": calculate_backoff(attempt, &config, None, 0.0).to_string() }))
        })();
        out.insert(id, result.unwrap_or_else(|e| json!({ "error": e })));
    }
    out
}

fn run_jitter(vectors: &[Value]) -> Map<String, Value> {
    let mut out = Map::new();
    for v in vectors {
        let id = v["id"].as_str().unwrap().to_string();
        let result = (|| -> Result<Value, String> {
            let strategy_str = v["strategy"].as_str().unwrap_or("default");
            let jitter = match strategy_str {
                "none" => JitterStrategy::None,
                "full" => JitterStrategy::Full,
                "equal" => JitterStrategy::Equal,
                "decorrelated" => JitterStrategy::Decorrelated,
                "default" => BackoffConfig::default().jitter,
                other => return Err(format!("unknown jitter strategy: {other}")),
            };
            let config = BackoffConfig {
                base_delay_ms: parse_u64(&v["base_delay_ms"])?,
                max_delay_ms: parse_u64(&v["max_delay_ms"])?,
                max_retries: 3,
                jitter,
            };
            let attempt = v["attempt"].as_u64().ok_or("attempt not u64")? as u32;
            let prev = match &v["prev_delay_ms"] {
                Value::Null => None,
                other => Some(parse_u64(other)?),
            };
            let factor = v["random_factor"].as_f64().ok_or("random_factor not f64")?;
            Ok(json!({ "value": calculate_backoff(attempt, &config, prev, factor).to_string() }))
        })();
        out.insert(id, result.unwrap_or_else(|e| json!({ "error": e })));
    }
    out
}

fn run_retry(vectors: &[Value], cfg: &Value) -> Map<String, Value> {
    let base = parse_u64(&cfg["base_delay_ms"]).unwrap();
    let max = parse_u64(&cfg["max_delay_ms"]).unwrap();
    let mut out = Map::new();
    for v in vectors {
        let id = v["id"].as_str().unwrap().to_string();
        let config = BackoffConfig {
            base_delay_ms: base,
            max_delay_ms: max,
            max_retries: v["max_retries"].as_u64().unwrap() as u32,
            jitter: JitterStrategy::None,
        };
        let decision = evaluate_response(
            v["status"].as_u64().unwrap() as u16,
            v["attempt"].as_u64().unwrap() as u32,
            &config,
            v["retry_after"].as_str(),
            None,
            0.0,
        );
        let obs = match decision {
            RetryDecision::Success => json!({ "decision": "Success" }),
            RetryDecision::Terminal => json!({ "decision": "Terminal" }),
            RetryDecision::Exhausted => json!({ "decision": "Exhausted" }),
            RetryDecision::Retry { delay_ms } => {
                json!({ "decision": "Retry", "delay_ms": delay_ms.to_string() })
            }
        };
        out.insert(id, obs);
    }
    out
}

fn run_circuit(vectors: &[Value]) -> Map<String, Value> {
    let mut out = Map::new();
    for v in vectors {
        let id = v["id"].as_str().unwrap().to_string();
        let mut cb = CircuitBreaker::new(
            v["failure_threshold"].as_u64().unwrap() as u32,
            v["cooldown_ms"].as_u64().unwrap(),
        );
        let mut steps = Vec::new();
        for step in v["steps"].as_array().unwrap() {
            let t = step["t"].as_u64().unwrap();
            let mut obs = Map::new();
            match step["op"].as_str().unwrap() {
                "record_failure" => cb.record_failure(t),
                "record_success" => cb.record_success(),
                "release_probe" => cb.release_probe(),
                "can_request" => {
                    obs.insert("ret".into(), json!(cb.can_request(t)));
                }
                "observe" => {}
                other => {
                    obs.insert("error".into(), json!(format!("unknown op {other}")));
                }
            }
            obs.insert("state".into(), json!(state_name(cb.state)));
            obs.insert("state_at".into(), json!(state_name(cb.state_at(t))));
            obs.insert("failure_count".into(), json!(cb.failure_count));
            steps.push(Value::Object(obs));
        }
        out.insert(id, Value::Array(steps));
    }
    out
}

fn main() {
    let path = env::args()
        .nth(1)
        .unwrap_or_else(|| "../config/differential_vectors.json".to_string());
    let raw = fs::read_to_string(&path).expect("failed to read vectors file");
    let doc: Value = serde_json::from_str(&raw).expect("invalid vectors JSON");

    let report = json!({
        "impl": "rust_direct",
        "results": {
            "backoff": run_backoff(doc["backoff"].as_array().unwrap()),
            "jitter": run_jitter(doc["jitter"].as_array().unwrap()),
            "backoff_numeric_boundary": run_backoff(doc["backoff_numeric_boundary"].as_array().unwrap()),
            "retry_policy": run_retry(doc["retry_policy"].as_array().unwrap(), &doc["retry_policy_config"]),
            "circuit_breaker": run_circuit(doc["circuit_breaker"].as_array().unwrap()),
        }
    });
    println!("{}", serde_json::to_string(&report).unwrap());
}

