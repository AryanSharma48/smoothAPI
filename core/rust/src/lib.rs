// Module declarations
pub mod backoff;
pub mod circuit;
pub mod policy;

// Re-exports for clean library consumer access
pub use backoff::{backoff, calculate_backoff, BackoffConfig, JitterStrategy};
pub use circuit::{CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState, CircuitState};
pub use policy::{
    evaluate_response, evaluate_response_with_retry_on, is_retryable_status, parse_retry_after,
    RetryDecision, DEFAULT_RETRY_ON,
};