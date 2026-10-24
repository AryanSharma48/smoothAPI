use napi_derive::napi;
use smooth_api_core::{
    BackoffConfig, CircuitBreaker, CircuitState, JitterStrategy, RetryDecision, calculate_backoff,
    evaluate_response,
};

#[napi]
pub fn noop_native(x: i64) -> i64 {
    std::hint::black_box(x)
}

fn parse_jitter_strategy(jitter: Option<&str>) -> JitterStrategy {
    match jitter {
        Some("full") => JitterStrategy::Full,
        Some("equal") => JitterStrategy::Equal,
        Some("decorrelated") => JitterStrategy::Decorrelated,
        Some("default") => BackoffConfig::default().jitter,
        _ => JitterStrategy::None,
    }
}

#[napi]
pub fn calculate_backoff_native(
    attempt: u32,
    base_delay_ms: i64,
    max_delay_ms: i64,
    jitter: Option<String>,
    prev_delay_ms: Option<i64>,
    random_factor: Option<f64>,
) -> i64 {
    let config = BackoffConfig {
        base_delay_ms: base_delay_ms.max(0) as u64,
        max_delay_ms: max_delay_ms.max(0) as u64,
        max_retries: 3,
        jitter: parse_jitter_strategy(jitter.as_deref()),
    };
    let prev = prev_delay_ms.map(|d| d.max(0) as u64);
    let factor = random_factor.unwrap_or(0.0);
    calculate_backoff(attempt, &config, prev, factor) as i64
}

#[napi(object)]
pub struct NativeRetryDecision {
    pub r#type: String,
    pub delay_ms: Option<i64>,
}

#[napi]
pub fn evaluate_response_native(
    status: u16,
    attempt: u32,
    base_delay_ms: i64,
    max_delay_ms: i64,
    max_retries: Option<u32>,
    retry_after_header: Option<String>,
) -> NativeRetryDecision {
    let config = BackoffConfig {
        base_delay_ms: base_delay_ms.max(0) as u64,
        max_delay_ms: max_delay_ms.max(0) as u64,
        max_retries: max_retries.unwrap_or(3),
        jitter: JitterStrategy::None,
    };

    let decision = evaluate_response(
        status,
        attempt,
        &config,
        retry_after_header.as_deref(),
        None,
        0.0,
    );

    match decision {
        RetryDecision::Success => NativeRetryDecision {
            r#type: "Success".to_string(),
            delay_ms: None,
        },
        RetryDecision::Terminal => NativeRetryDecision {
            r#type: "Terminal".to_string(),
            delay_ms: None,
        },
        RetryDecision::Exhausted => NativeRetryDecision {
            r#type: "Exhausted".to_string(),
            delay_ms: None,
        },
        RetryDecision::Retry { delay_ms } => NativeRetryDecision {
            r#type: "Retry".to_string(),
            delay_ms: Some(delay_ms as i64),
        },
    }
}

#[napi]
pub struct NativeCircuitBreaker {
    inner: CircuitBreaker,
}

#[napi]
impl NativeCircuitBreaker {
    #[napi(constructor)]
    pub fn new(failure_threshold: Option<u32>, cooldown_ms: Option<i64>) -> Self {
        let threshold = failure_threshold.unwrap_or(3);
        let cooldown = cooldown_ms.unwrap_or(10_000).max(0) as u64;
        Self {
            inner: CircuitBreaker::new(threshold, cooldown),
        }
    }

    #[napi]
    pub fn can_request(&mut self, now_ms: i64) -> bool {
        self.inner.can_request(now_ms.max(0) as u64)
    }

    #[napi]
    pub fn record_success(&mut self) {
        self.inner.record_success();
    }

    #[napi]
    pub fn record_failure(&mut self, now_ms: i64) {
        self.inner.record_failure(now_ms.max(0) as u64);
    }

    #[napi]
    pub fn release_probe(&mut self) {
        self.inner.release_probe();
    }

    #[napi(getter)]
    pub fn state(&self) -> String {
        match self.inner.state {
            CircuitState::Closed => "CLOSED".to_string(),
            CircuitState::Open => "OPEN".to_string(),
            CircuitState::HalfOpen => "HALF_OPEN".to_string(),
        }
    }

    #[napi]
    pub fn state_at(&self, now_ms: i64) -> String {
        match self.inner.state_at(now_ms.max(0) as u64) {
            CircuitState::Closed => "CLOSED".to_string(),
            CircuitState::Open => "OPEN".to_string(),
            CircuitState::HalfOpen => "HALF_OPEN".to_string(),
        }
    }

    #[napi(getter)]
    pub fn failure_count(&self) -> u32 {
        self.inner.failure_count
    }
}
