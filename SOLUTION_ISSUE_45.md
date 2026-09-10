# Solution for Issue #45

## 🛠️ Proposed Solution (by Aditya Waghamare)

### Analysis
To achieve feature parity with the TypeScript/JS version of smoothAPI, we need to implement `onRetry` and `onCircuitStateChange` lifecycle hooks in the Python package. These hooks allow developers to monitor retry attempts and circuit breaker state transitions (e.g., closed -> open -> half-open) for robust telemetry and error handling.

### Fix
Add `on_retry` and `on_circuit_state_change` callbacks to the client configuration/options and trigger them appropriately inside the retry and circuit breaker logic.

### Implementation
```python
from typing import Callable, Optional, Any
import time
import logging

logger = logging.getLogger("smoothAPI")

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_time: float = 30.0,
        on_circuit_state_change: Optional[Callable[[str, str], None]] = None
    ):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.on_circuit_state_change = on_circuit_state_change
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failure_count = 0
        self.last_failure_time = 0.0

    def _set_state(self, new_state: str):
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"Circuit breaker state changed from {old_state} to {new_state}")
            if self.on_circuit_state_change:
                try:
                    self.on_circuit_state_change(old_state, new_state)
                except Exception as e:
                    logger.error(f"Error in on_circuit_state_change callback: {e}")

class SmoothAPIClient:
    def __init__(
        self,
        base_url: str,
        retries: int = 3,
        backoff_factor: float = 1.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        on_circuit_state_change: Optional[Callable[[str, str], None]] = None
    ):
        self.base_url = base_url
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.on_retry = on_retry
        
        if circuit_breaker:
            self.circuit_breaker = circuit_breaker
            if on_circuit_state_change and not self.circuit_breaker.on_circuit_state_change:
                self.circuit_breaker.on_circuit_state_change = on_circuit_state_change
        else:
            self.circuit_breaker = CircuitBreaker(on_circuit_state_change=on_circuit_state_change)

    def request_with_retry(self, func: Callable[[], Any]) -> Any:
        attempt = 0
        while attempt <= self.retries:
            try:
                # Check circuit breaker state
                if self.circuit_breaker.state == "OPEN":
                    if time.time() - self.circuit_breaker.last_failure_time > self.circuit_breaker.recovery_time:
                        self.circuit_breaker._set_state("HALF-OPEN")
                    else:
                        raise Exception("Circuit breaker is OPEN")

                result = func()

                # Success resets circuit if half-open or closed
                if self.circuit_breaker.state == "HALF-OPEN":
                    self.circuit_breaker._set_state("CLOSED")
                    self.circuit_breaker.failure_count = 0

                return result

            except Exception as e:
                attempt += 1
                self.circuit_breaker.failure_count += 1
                self.circuit_breaker.last_failure_time = time.time()

                if self.circuit_breaker.failure_count >= self.circuit_breaker.failure_threshold:
                    self.circuit_breaker._set_state("OPEN")

                if attempt > self.retries:
                    raise e

                if self.on_retry:
                    try:
                        self.on_retry(e, attempt)
                    except Exception as cb_err:
                        logger.error(f"Error in on_retry callback: {cb_err}")

                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                time.sleep(sleep_time)
```

### Testing
- Verified callback invocation order during simulated network failures and recoveries.
- Ensured state transitions correctly fire `on_circuit_state_change`.

Signed-off-by: Aditya Waghamare <adityawaghamare7620@gmail.com>


---
*Submitted by Aditya Waghamare*
💰 **Payout Address (Base L2 / EVM):** `0xb61dBcdBc3407F71EaCb64D4CBFAcf9FFfe2415C`