"""
hf_throttle.py
==============
Client-side rate limiter for the Hugging Face Hub API quota
(1000 requests / 5 minutes on the "api" bucket, shared by every call:
commits, preuploads, repo tree listings, whoami, ...).

All hub calls — including the 8 worker threads spawned inside
upload_large_folder() — go through huggingface_hub's shared HTTP client
(an httpx.Client, huggingface_hub.utils._http.get_session(); every call
funnels through client.request(...)). We wrap that client's request()
with:

  1. A thread-safe sliding-window limiter that paces requests to stay
     under a configurable budget (default 900 req / 300 s, i.e. a safety
     margin under the server's 1000/5min so unrelated calls never trip
     the 429).
  2. A safety net: if a 429 still slips through (e.g. another machine on
     the same account is spending the same quota), sleep for the
     Retry-After header (or an exponential fallback) and retry the
     request instead of letting the error propagate — the upload never
     aborts, it just waits out the window.

The limiter blocks in acquire(), which parks the calling worker thread;
generation progress bars are unaffected (they poll on timers).
"""

import threading
import time
from collections import deque

DEFAULT_MAX_REQUESTS = 900      # server quota is 1000 — keep a margin
DEFAULT_PERIOD_SECONDS = 300.0  # 5 minutes


class SlidingWindowLimiter:
    """At most `max_calls` acquisitions per `period` seconds, across all
    threads. Calls that exceed the budget block until a slot frees up."""

    def __init__(self, max_calls, period_seconds):
        self.max_calls = max(1, int(max_calls))
        self.period = float(period_seconds)
        self._lock = threading.Lock()
        self._timestamps = deque()
        self.total_throttled_waits = 0  # stats, for the startup log line

    def acquire(self):
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self.period:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                # Window is full: wait until the oldest request ages out
                # (plus a small epsilon so we don't spin on the boundary).
                wait = self.period - (now - self._timestamps[0]) + 0.05
                self.total_throttled_waits += 1
            time.sleep(max(wait, 0.1))


def _parse_retry_after(response, fallback_seconds):
    try:
        value = float(response.headers.get("Retry-After", "").strip())
        if value > 0:
            return value
    except (ValueError, AttributeError):
        pass
    return fallback_seconds


def install(max_requests=DEFAULT_MAX_REQUESTS, period_seconds=DEFAULT_PERIOD_SECONDS, verbose=True):
    """Patch huggingface_hub's shared session with the throttled request.
    Idempotent — safe to call more than once. Must run before the first
    hub API call (e.g. right before login())."""
    from huggingface_hub.utils import _http

    session = _http.get_session()
    if getattr(session, "_hf_throttled", False):
        return

    limiter = SlidingWindowLimiter(max_requests, period_seconds)
    original_request = session.request

    def throttled_request(method, url, *args, **kwargs):
        limiter.acquire()
        backoff = 30.0
        while True:
            response = original_request(method, url, *args, **kwargs)
            if response.status_code != 429:
                return response
            wait = _parse_retry_after(response, backoff)
            if verbose:
                print(f"[hf-throttle] 429 from {url} — waiting {wait:.0f}s then retrying")
            time.sleep(wait)
            backoff = min(backoff * 2, 300.0)

    session.request = throttled_request
    session._hf_throttled = True
    if verbose:
        print(f"[hf-throttle] Hub API rate limiter installed: "
              f"{limiter.max_calls} requests / {limiter.period:.0f}s "
              f"(server quota 1000/300s)")
    return limiter
