import time
import random

def calculate_backoff(attempt: int, config) -> float:
    exponential = config.base_delay * (2 ** attempt)
    capped = min(config.max_delay, exponential)
    return random.uniform(0, capped)


def sleep_backoff(seconds: float) -> None:
    time.sleep(seconds)


