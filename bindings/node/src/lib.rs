use napi_derive::napi;
use smooth_api_core::{calculate_backoff, BackoffConfig, JitterStrategy};

#[napi]
pub fn calculate_backoff_native(attempt: u32, base_delay_ms: i64, max_delay_ms: i64) -> i64 {
    let config = BackoffConfig {
        base_delay_ms: base_delay_ms.max(0) as u64,
        max_delay_ms: max_delay_ms.max(0) as u64,
        max_retries: 3,
        jitter: JitterStrategy::None,
    };
    calculate_backoff(attempt, &config, None, 0.0) as i64
}
