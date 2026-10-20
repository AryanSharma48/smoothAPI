// Module declarations
pub mod backoff;
pub mod circuit;
pub mod policy;

// Re-exports for clean library consumer access
pub use backoff::{BackoffConfig, JitterStrategy, backoff, calculate_backoff};
pub use circuit::{CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState, CircuitState};
pub use policy::{
    DEFAULT_RETRY_ON, RetryDecision, evaluate_response, evaluate_response_with_retry_on,
    is_retryable_status, parse_retry_after,
};
