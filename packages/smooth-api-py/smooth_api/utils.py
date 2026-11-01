import random
import time


def _compute_capped_delay(base_delay: float, max_delay: float, attempt: int) -> float:
    if base_delay <= 0.0 or max_delay <= 0.0:
        return 0.0
    if base_delay >= max_delay:
        return max_delay
    remaining = max(0, int(attempt))
    current = base_delay
    while remaining > 0 and current < max_delay:
        step = min(remaining, 52)
        current *= 2.0 ** step
        remaining -= step
    return min(max_delay, current)


def calculate_backoff(
    attempt: int,
    config,
    prev_delay: float | None = None,
    random_factor: float | None = None,
) -> float:
    base_delay = max(0.0, float(config.base_delay))
    max_delay = max(0.0, float(config.max_delay))
    capped = _compute_capped_delay(base_delay, max_delay, attempt)
    if capped == 0.0:
        return 0.0

    factor = (
        max(0.0, min(1.0, float(random_factor)))
        if random_factor is not None
        else random.random()
    )
    strategy = getattr(config, "jitter", "equal") or "equal"
    if strategy == "none":
        return capped
    if strategy == "full":
        return capped * factor
    if strategy == "decorrelated":
        base = prev_delay if prev_delay is not None else base_delay
        upper_bound = max(base_delay, base * 3.0)
        return min(max_delay, base_delay + (upper_bound - base_delay) * factor)
    half = capped / 2.0
    return half + half * factor


def sleep_backoff(seconds: float) -> None:
    time.sleep(seconds)
