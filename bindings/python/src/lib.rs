use pyo3::prelude::*;
use std::sync::Mutex;
use smooth_api_core::{
    BackoffConfig, CircuitBreaker, CircuitState, JitterStrategy, RetryDecision, calculate_backoff,
    evaluate_response,
};

/// Represents the decision made by the retry policy.
#[pyclass]
#[derive(Clone)]
pub struct NativeRetryDecision {
    #[pyo3(get)]
    pub r#type: String,
    #[pyo3(get)]
    pub delay_ms: Option<i64>,
}

#[pymethods]
impl NativeRetryDecision {
    fn __repr__(&self) -> String {
        format!(
            "NativeRetryDecision(type='{}', delay_ms={:?})",
            self.r#type, self.delay_ms
        )
    }
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

/// Minimal no-op function to measure raw PyO3 FFI boundary round-trip cost.
#[pyfunction]
pub fn noop_native(x: i64) -> i64 {
    std::hint::black_box(x)
}

/// Minimal no-op function that releases and reacquires the GIL via py.allow_threads.
#[pyfunction]
pub fn noop_nogil(py: Python<'_>, x: i64) -> i64 {
    py.allow_threads(move || std::hint::black_box(x))
}

/// Calculate exponential backoff in milliseconds with optional jitter strategy (GIL held).
#[pyfunction]
#[pyo3(signature = (attempt, base_delay_ms, max_delay_ms, jitter = None, prev_delay_ms = None, random_factor = None))]
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

/// Calculate exponential backoff in milliseconds while releasing the Python GIL.
#[pyfunction]
#[pyo3(signature = (attempt, base_delay_ms, max_delay_ms, jitter = None, prev_delay_ms = None, random_factor = None))]
pub fn calculate_backoff_nogil(
    py: Python<'_>,
    attempt: u32,
    base_delay_ms: i64,
    max_delay_ms: i64,
    jitter: Option<String>,
    prev_delay_ms: Option<i64>,
    random_factor: Option<f64>,
) -> i64 {
    py.allow_threads(move || {
        let config = BackoffConfig {
            base_delay_ms: base_delay_ms.max(0) as u64,
            max_delay_ms: max_delay_ms.max(0) as u64,
            max_retries: 3,
            jitter: parse_jitter_strategy(jitter.as_deref()),
        };
        let prev = prev_delay_ms.map(|d| d.max(0) as u64);
        let factor = random_factor.unwrap_or(0.0);
        calculate_backoff(attempt, &config, prev, factor) as i64
    })
}

/// Evaluate an HTTP response status code and optional Retry-After header.
#[pyfunction]
#[pyo3(signature = (status, attempt, base_delay_ms, max_delay_ms, max_retries = None, retry_after_header = None))]
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

/// Thread-safe Native Circuit Breaker wrapping the core Rust finite-state machine.
#[pyclass]
pub struct NativeCircuitBreaker {
    inner: Mutex<CircuitBreaker>,
}

#[pymethods]
impl NativeCircuitBreaker {
    #[new]
    #[pyo3(signature = (failure_threshold = None, cooldown_ms = None))]
    pub fn new(failure_threshold: Option<u32>, cooldown_ms: Option<i64>) -> Self {
        let threshold = failure_threshold.unwrap_or(3);
        let cooldown = cooldown_ms.unwrap_or(10_000).max(0) as u64;
        Self {
            inner: Mutex::new(CircuitBreaker::new(threshold, cooldown)),
        }
    }

    pub fn can_request(&self, now_ms: i64) -> bool {
        let mut guard = self.inner.lock().unwrap();
        guard.can_request(now_ms.max(0) as u64)
    }

    pub fn can_request_nogil(&self, py: Python<'_>, now_ms: i64) -> bool {
        let inner = &self.inner;
        py.allow_threads(move || {
            let mut guard = inner.lock().unwrap();
            guard.can_request(now_ms.max(0) as u64)
        })
    }

    pub fn record_success(&self) {
        let mut guard = self.inner.lock().unwrap();
        guard.record_success();
    }

    pub fn record_success_nogil(&self, py: Python<'_>) {
        let inner = &self.inner;
        py.allow_threads(move || {
            let mut guard = inner.lock().unwrap();
            guard.record_success();
        });
    }

    pub fn record_failure(&self, now_ms: i64) {
        let mut guard = self.inner.lock().unwrap();
        guard.record_failure(now_ms.max(0) as u64);
    }

    pub fn record_failure_nogil(&self, py: Python<'_>, now_ms: i64) {
        let inner = &self.inner;
        py.allow_threads(move || {
            let mut guard = inner.lock().unwrap();
            guard.record_failure(now_ms.max(0) as u64);
        });
    }

    pub fn release_probe(&self) {
        let mut guard = self.inner.lock().unwrap();
        guard.release_probe();
    }

    #[getter]
    pub fn state(&self) -> String {
        let guard = self.inner.lock().unwrap();
        match guard.state {
            CircuitState::Closed => "CLOSED".to_string(),
            CircuitState::Open => "OPEN".to_string(),
            CircuitState::HalfOpen => "HALF_OPEN".to_string(),
        }
    }

    pub fn state_at(&self, now_ms: i64) -> String {
        let guard = self.inner.lock().unwrap();
        match guard.state_at(now_ms.max(0) as u64) {
            CircuitState::Closed => "CLOSED".to_string(),
            CircuitState::Open => "OPEN".to_string(),
            CircuitState::HalfOpen => "HALF_OPEN".to_string(),
        }
    }

    #[getter]
    pub fn failure_count(&self) -> u32 {
        let guard = self.inner.lock().unwrap();
        guard.failure_count
    }

    fn __repr__(&self) -> String {
        let guard = self.inner.lock().unwrap();
        format!(
            "NativeCircuitBreaker(state='{}', failure_count={})",
            match guard.state {
                CircuitState::Closed => "CLOSED",
                CircuitState::Open => "OPEN",
                CircuitState::HalfOpen => "HALF_OPEN",
            },
            guard.failure_count
        )
    }
}

/// SmoothAPI native Python extension module.
#[pymodule]
fn smoothapi_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(noop_native, m)?)?;
    m.add_function(wrap_pyfunction!(noop_nogil, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_backoff_native, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_backoff_nogil, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_response_native, m)?)?;
    m.add_class::<NativeRetryDecision>()?;
    m.add_class::<NativeCircuitBreaker>()?;
    Ok(())
}

