use std::collections::HashMap;

// Circuit breaker state lifecycle
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CircuitState {
    Closed,
    Open,
    HalfOpen,
}

// Single domain circuit breaker tracking failure count and cooldown
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CircuitBreaker {
    pub failure_threshold: u32,
    pub cooldown_ms: u64,
    pub state: CircuitState,
    pub failure_count: u32,
    pub last_failure_time_ms: u64,
}

impl Default for CircuitBreaker {
    fn default() -> Self {
        Self::new(3, 10_000)
    }
}

impl CircuitBreaker {
    pub fn new(failure_threshold: u32, cooldown_ms: u64) -> Self {
        Self {
            failure_threshold,
            cooldown_ms,
            state: CircuitState::Closed,
            failure_count: 0,
            last_failure_time_ms: 0,
        }
    }

    // Determine if request is allowed, transitioning Open -> HalfOpen when cooldown expires
    pub fn can_request(&mut self, now_ms: u64) -> bool {
        match self.state {
            CircuitState::Closed | CircuitState::HalfOpen => true,
            CircuitState::Open => {
                if now_ms.saturating_sub(self.last_failure_time_ms) > self.cooldown_ms {
                    self.state = CircuitState::HalfOpen;
                    true
                } else {
                    false
                }
            }
        }
    }

    // Reset failure counter and transition back to Closed
    pub fn record_success(&mut self) {
        self.failure_count = 0;
        self.state = CircuitState::Closed;
    }

    // Record failure, immediately tripping back to Open if in HalfOpen or threshold reached
    pub fn record_failure(&mut self, now_ms: u64) {
        self.failure_count = self.failure_count.saturating_add(1);

        if self.state == CircuitState::HalfOpen || self.failure_count >= self.failure_threshold {
            self.state = CircuitState::Open;
            self.last_failure_time_ms = now_ms;
        }
    }
}

// Configuration options for circuit breakers
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CircuitBreakerConfig {
    pub failure_threshold: u32,
    pub cooldown_ms: u64,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 3,
            cooldown_ms: 10_000,
        }
    }
}

// Per-domain circuit breaker registry matching SmoothAPI state map
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CircuitBreakerState {
    pub config: CircuitBreakerConfig,
    circuits: HashMap<String, CircuitBreaker>,
}

impl Default for CircuitBreakerState {
    fn default() -> Self {
        Self::new(CircuitBreakerConfig::default())
    }
}

impl CircuitBreakerState {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            config,
            circuits: HashMap::new(),
        }
    }

    // Get an existing circuit breaker or initialize a new one for the domain
    fn get_or_create(&mut self, domain: &str) -> &mut CircuitBreaker {
        let threshold = self.config.failure_threshold;
        let cooldown = self.config.cooldown_ms;
        self.circuits
            .entry(domain.to_string())
            .or_insert_with(|| CircuitBreaker::new(threshold, cooldown))
    }

    // Check if requests to the given domain are permitted
    pub fn can_request(&mut self, domain: &str, now_ms: u64) -> bool {
        self.get_or_create(domain).can_request(now_ms)
    }

    // Record a successful response for the domain
    pub fn record_success(&mut self, domain: &str) {
        self.get_or_create(domain).record_success();
    }

    // Record a failure for the domain
    pub fn record_failure(&mut self, domain: &str, now_ms: u64) {
        self.get_or_create(domain).record_failure(now_ms);
    }

    // Read the current state of a domain without mutating the map
    pub fn get_state(&self, domain: &str) -> CircuitState {
        self.circuits
            .get(domain)
            .map(|b| b.state)
            .unwrap_or(CircuitState::Closed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_closed_and_allows_requests() {
        let mut breaker = CircuitBreaker::new(3, 10_000);
        assert_eq!(breaker.state, CircuitState::Closed);
        assert!(breaker.can_request(1000));
    }

    #[test]
    fn trips_open_after_reaching_failure_threshold() {
        let mut breaker = CircuitBreaker::new(3, 10_000);

        breaker.record_failure(1000);
        assert_eq!(breaker.state, CircuitState::Closed);

        breaker.record_failure(2000);
        assert_eq!(breaker.state, CircuitState::Closed);

        breaker.record_failure(3000);
        assert_eq!(breaker.state, CircuitState::Open);
        assert_eq!(breaker.last_failure_time_ms, 3000);

        assert!(!breaker.can_request(4000));
    }

    #[test]
    fn transitions_to_half_open_after_cooldown() {
        let mut breaker = CircuitBreaker::new(3, 10_000);

        breaker.record_failure(1000);
        breaker.record_failure(2000);
        breaker.record_failure(3000);
        assert_eq!(breaker.state, CircuitState::Open);

        assert!(!breaker.can_request(12_999));
        assert!(!breaker.can_request(13_000));

        assert!(breaker.can_request(13_001));
        assert_eq!(breaker.state, CircuitState::HalfOpen);
    }

    #[test]
    fn resets_to_closed_on_success() {
        let mut breaker = CircuitBreaker::new(3, 10_000);

        breaker.record_failure(1000);
        breaker.record_failure(2000);
        breaker.record_failure(3000);
        assert_eq!(breaker.state, CircuitState::Open);

        assert!(breaker.can_request(15_000));
        assert_eq!(breaker.state, CircuitState::HalfOpen);

        breaker.record_success();
        assert_eq!(breaker.state, CircuitState::Closed);
        assert_eq!(breaker.failure_count, 0);
        assert!(breaker.can_request(16_000));
    }

    #[test]
    fn reopens_immediately_if_half_open_request_fails() {
        let mut breaker = CircuitBreaker::new(3, 10_000);

        breaker.record_failure(1000);
        breaker.record_failure(2000);
        breaker.record_failure(3000);

        assert!(breaker.can_request(15_000));
        assert_eq!(breaker.state, CircuitState::HalfOpen);

        breaker.record_failure(15_100);
        assert_eq!(breaker.state, CircuitState::Open);
        assert_eq!(breaker.last_failure_time_ms, 15_100);
        assert!(!breaker.can_request(16_000));
    }

    #[test]
    fn tracks_independent_circuit_states_per_domain() {
        let mut state = CircuitBreakerState::default();

        let stripe = "api.stripe.com";
        let github = "api.github.com";

        assert_eq!(state.get_state(stripe), CircuitState::Closed);
        assert_eq!(state.get_state(github), CircuitState::Closed);

        state.record_failure(stripe, 1000);
        state.record_failure(stripe, 2000);
        state.record_failure(stripe, 3000);

        assert_eq!(state.get_state(stripe), CircuitState::Open);
        assert!(!state.can_request(stripe, 4000));

        assert_eq!(state.get_state(github), CircuitState::Closed);
        assert!(state.can_request(github, 4000));

        state.record_success(github);
        assert_eq!(state.get_state(github), CircuitState::Closed);
    }
}
