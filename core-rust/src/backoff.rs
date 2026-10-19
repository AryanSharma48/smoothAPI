pub struct BackoffConfig {
    pub base_delay_ms: u64,
    pub max_delay_ms: u64,
}

pub fn backoff(attempt: u32, config: &BackoffConfig) -> u64 {
    let exponential = config.base_delay_ms.saturating_mul(2u64.saturating_pow(attempt));
    exponential.min(config.max_delay_ms)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn calculates_backoff() {
        let config = BackoffConfig {
            base_delay_ms: 100,
            max_delay_ms: 1000,
        };

        assert_eq!(backoff(0, &config), 100);
        assert_eq!(backoff(1, &config), 200);
        assert_eq!(backoff(2, &config), 400);
        assert_eq!(backoff(3, &config), 800);
    }

    #[test]
    fn caps_at_max_delay() {
        let config = BackoffConfig {
            base_delay_ms: 100,
            max_delay_ms: 1000,
        };

        assert_eq!(backoff(4, &config), 1000);
    }

    #[test]
    fn does_not_overflow_on_large_attempts() {
        let config = BackoffConfig {
            base_delay_ms: 100,
            max_delay_ms: 1000,
        };

        let delay = backoff(100, &config);
        assert_eq!(delay, 1000);
    }
}