# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time

import httpx


class RateLimiter:
    def __init__(self, delay_sec: float) -> None:
        self.delay_sec = max(0.0, delay_sec)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self.delay_sec <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
            self._next = time.monotonic() + self.delay_sec


def make_client(user_agent: str, timeout_sec: float, *, verify: bool = True) -> httpx.Client:
    timeout = httpx.Timeout(timeout_sec, connect=min(8.0, timeout_sec))
    return httpx.Client(
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "uk,ru;q=0.9,en;q=0.5",
        },
        timeout=timeout,
        follow_redirects=True,
        verify=verify,
        limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
    )
