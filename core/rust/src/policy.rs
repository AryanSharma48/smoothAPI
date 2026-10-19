use crate::backoff::{calculate_backoff, BackoffConfig};

// Default HTTP status codes eligible for retry
pub const DEFAULT_RETRY_ON: [u16; 5] = [429, 500, 502, 503, 504];

// Outcome decision after evaluating an HTTP response
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryDecision {
    Success,
    Retry { delay_ms: u64 },
    Exhausted,
    Terminal,
}

// Parses positive integer seconds from Retry-After header and converts to milliseconds
pub fn parse_retry_after(header: &str) -> Option<u64> {
    header
        .trim()
        .parse::<u64>()
        .ok()
        .filter(|&seconds| seconds > 0)
        .map(|seconds| seconds.saturating_mul(1000))
}

// Checks if the response status is in the retryable status list
pub fn is_retryable_status(status: u16, retry_on: &[u16]) -> bool {
    retry_on.contains(&status)
}

// Evaluates HTTP response using default retryable status codes
pub fn evaluate_response(
    status: u16,
    attempt: u32,
    config: &BackoffConfig,
    retry_after_header: Option<&str>,
    prev_delay_ms: Option<u64>,
    random_factor: f64,
) -> RetryDecision {
    evaluate_response_with_retry_on(
        status,
        attempt,
        config,
        &DEFAULT_RETRY_ON,
        retry_after_header,
        prev_delay_ms,
        random_factor,
    )
}

// Evaluates HTTP response against a custom list of retryable status codes
pub fn evaluate_response_with_retry_on(
    status: u16,
    attempt: u32,
    config: &BackoffConfig,
    retry_on: &[u16],
    retry_after_header: Option<&str>,
    prev_delay_ms: Option<u64>,
    random_factor: f64,
) -> RetryDecision {
    // 2xx response indicates success
    if (200..300).contains(&status) {
        return RetryDecision::Success;
    }

    // Status is not configured as retryable (client error, non-retryable 4xx)
    if !is_retryable_status(status, retry_on) {
        return RetryDecision::Terminal;
    }

    // Attempt count exceeded max_retries limit
    if !config.should_retry(attempt) {
        return RetryDecision::Exhausted;
    }

    // Prefer Retry-After header for 429 rate limit responses
    let delay_ms = if status == 429 {
        retry_after_header
            .and_then(parse_retry_after)
            .unwrap_or_else(|| calculate_backoff(attempt, config, prev_delay_ms, random_factor))
    } else {
        calculate_backoff(attempt, config, prev_delay_ms, random_factor)
    };

    RetryDecision::Retry { delay_ms }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backoff::JitterStrategy;

    fn test_config() -> BackoffConfig {
        BackoffConfig {
            base_delay_ms: 100,
            max_delay_ms: 5000,
            max_retries: 3,
            jitter: JitterStrategy::None,
        }
    }

    #[test]
    fn success_on_2xx_responses() {
        let config = test_config();
        assert_eq!(evaluate_response(200, 0, &config, None, None, 0.0), RetryDecision::Success);
        assert_eq!(evaluate_response(201, 0, &config, None, None, 0.0), RetryDecision::Success);
        assert_eq!(evaluate_response(204, 0, &config, None, None, 0.0), RetryDecision::Success);
    }

    #[test]
    fn terminal_on_client_errors() {
        let config = test_config();
        assert_eq!(evaluate_response(400, 0, &config, None, None, 0.0), RetryDecision::Terminal);
        assert_eq!(evaluate_response(401, 0, &config, None, None, 0.0), RetryDecision::Terminal);
        assert_eq!(evaluate_response(403, 0, &config, None, None, 0.0), RetryDecision::Terminal);
        assert_eq!(evaluate_response(404, 0, &config, None, None, 0.0), RetryDecision::Terminal);
    }

    #[test]
    fn retries_on_server_errors_with_backoff() {
        let config = test_config();

        assert_eq!(
            evaluate_response(500, 0, &config, None, None, 0.0),
            RetryDecision::Retry { delay_ms: 100 }
        );
        assert_eq!(
            evaluate_response(502, 1, &config, None, None, 0.0),
            RetryDecision::Retry { delay_ms: 200 }
        );
        assert_eq!(
            evaluate_response(503, 2, &config, None, None, 0.0),
            RetryDecision::Retry { delay_ms: 400 }
        );
    }

    #[test]
    fn exhausts_when_reaching_max_retries() {
        let config = test_config(); // max_retries = 3

        assert_eq!(
            evaluate_response(500, 3, &config, None, None, 0.0),
            RetryDecision::Exhausted
        );
        assert_eq!(
            evaluate_response(500, 4, &config, None, None, 0.0),
            RetryDecision::Exhausted
        );
    }

    #[test]
    fn parses_and_respects_retry_after_header_on_429() {
        let config = test_config();

        let decision = evaluate_response(429, 0, &config, Some("5"), None, 0.0);
        assert_eq!(decision, RetryDecision::Retry { delay_ms: 5000 });
    }

    #[test]
    fn falls_back_to_backoff_on_invalid_retry_after() {
        let config = test_config();

        let decision = evaluate_response(429, 0, &config, Some("invalid"), None, 0.0);
        assert_eq!(decision, RetryDecision::Retry { delay_ms: 100 });
    }
}
