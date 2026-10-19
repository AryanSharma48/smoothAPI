// Jitter strategy options for spreading retry intervals
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JitterStrategy {
    None,
    Full,
    Equal,
    Decorrelated,
}

// Configuration parameters for exponential backoff and retries
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BackoffConfig {
    pub base_delay_ms: u64,
    pub max_delay_ms: u64,
    pub max_retries: u32,
    pub jitter: JitterStrategy,
}

impl Default for BackoffConfig {
    // Default configuration matching SmoothAPI specifications
    fn default() -> Self {
        Self {
            base_delay_ms: 100,
            max_delay_ms: 30_000,
            max_retries: 3,
            jitter: JitterStrategy::Equal,
        }
    }
}

impl BackoffConfig {
    // Check if the current attempt is below the maximum allowed retries
    pub fn should_retry(&self, attempt: u32) -> bool {
        attempt < self.max_retries
    }
}

// Calculates backoff delay with jitter, matching SmoothAPI TS and Python logic
pub fn calculate_backoff(
    attempt: u32,
    config: &BackoffConfig,
    prev_delay_ms: Option<u64>,
    random_factor: f64,
) -> u64 {
    // Compute exponential delay with safe overflow saturation
    let exponential = config.base_delay_ms.saturating_mul(2u64.saturating_pow(attempt));
    let capped = exponential.min(config.max_delay_ms);
    let factor = random_factor.clamp(0.0, 1.0);

    // Apply the configured jitter strategy
    match config.jitter {
        JitterStrategy::None => capped,
        JitterStrategy::Full => (capped as f64 * factor).floor() as u64,
        JitterStrategy::Equal => {
            let half = capped / 2;
            half.saturating_add((half as f64 * factor).floor() as u64)
        }
        JitterStrategy::Decorrelated => {
            let base = prev_delay_ms.unwrap_or(config.base_delay_ms);
            let upper_bound = base.saturating_mul(3);
            let spread = upper_bound.saturating_sub(config.base_delay_ms);
            let random_delay = config
                .base_delay_ms
                .saturating_add((spread as f64 * factor).floor() as u64);
            random_delay.min(config.max_delay_ms)
        }
    }
}

// Convenience helper for deterministic backoff without jitter
pub fn backoff(attempt: u32, config: &BackoffConfig) -> u64 {
    calculate_backoff(attempt, config, None, 0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config(jitter: JitterStrategy) -> BackoffConfig {
        BackoffConfig {
            base_delay_ms: 100,
            max_delay_ms: 1000,
            max_retries: 3,
            jitter,
        }
    }

    #[test]
    fn calculates_exponential_backoff_without_jitter() {
        let config = test_config(JitterStrategy::None);

        assert_eq!(calculate_backoff(0, &config, None, 0.0), 100);
        assert_eq!(calculate_backoff(1, &config, None, 0.0), 200);
        assert_eq!(calculate_backoff(2, &config, None, 0.0), 400);
        assert_eq!(calculate_backoff(3, &config, None, 0.0), 800);
        assert_eq!(calculate_backoff(4, &config, None, 0.0), 1000); // capped at max_delay_ms
    }

    #[test]
    fn full_jitter_scales_from_zero_to_capped() {
        let config = test_config(JitterStrategy::Full);

        // At attempt 2, capped is 400ms
        assert_eq!(calculate_backoff(2, &config, None, 0.0), 0);
        assert_eq!(calculate_backoff(2, &config, None, 0.5), 200);
        assert_eq!(calculate_backoff(2, &config, None, 1.0), 400);
    }

    #[test]
    fn equal_jitter_scales_between_half_and_capped() {
        let config = test_config(JitterStrategy::Equal);

        // At attempt 2, capped = 400ms, half = 200ms
        assert_eq!(calculate_backoff(2, &config, None, 0.0), 200);
        assert_eq!(calculate_backoff(2, &config, None, 0.5), 300);
        assert_eq!(calculate_backoff(2, &config, None, 1.0), 400);
    }

    #[test]
    fn decorrelated_jitter_uses_previous_delay() {
        let config = test_config(JitterStrategy::Decorrelated);

        // base = 200 (prev_delay), upper_bound = 600, spread = 500
        // delay = 100 + 0.5 * 500 = 350
        let delay = calculate_backoff(1, &config, Some(200), 0.5);
        assert_eq!(delay, 350);
    }

    #[test]
    fn should_retry_respects_max_retries() {
        let config = BackoffConfig::default(); // max_retries = 3

        assert!(config.should_retry(0));
        assert!(config.should_retry(1));
        assert!(config.should_retry(2));
        assert!(!config.should_retry(3));
        assert!(!config.should_retry(4));
    }

    #[test]
    fn does_not_overflow_on_large_attempts() {
        let config = test_config(JitterStrategy::None);
        let delay = calculate_backoff(100, &config, None, 0.0);
        assert_eq!(delay, 1000);
    }
}