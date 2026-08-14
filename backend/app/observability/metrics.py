from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.requests = Counter()
        self.errors = Counter()
        self.latency_ms_total = 0.0

    def observe_request(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self.requests[(method, path, status_code)] += 1
            self.latency_ms_total += latency_ms

    def observe_error(self, path: str, code: str) -> None:
        with self._lock:
            self.errors[(path, code)] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "requests": {f"{method} {path} {status}": count for (method, path, status), count in self.requests.items()},
                "errors": {f"{path} {code}": count for (path, code), count in self.errors.items()},
                "latency_ms_total": round(self.latency_ms_total, 3),
            }

    def prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP quant_http_requests_total Total HTTP requests handled.",
            "# TYPE quant_http_requests_total counter",
        ]
        for key, count in snapshot["requests"].items():
            method, path, status = key.split(" ", 2)
            lines.append(f'quant_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')
        lines.extend([
            "# HELP quant_http_latency_ms_total Sum of request latency in milliseconds.",
            "# TYPE quant_http_latency_ms_total counter",
            f'quant_http_latency_ms_total {snapshot["latency_ms_total"]}',
        ])
        return "\n".join(lines) + "\n"


metrics = Metrics()
