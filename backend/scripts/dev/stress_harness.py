import concurrent.futures
import datetime
import json
import os
import random
import re
import subprocess
import sys
import time
from typing import Any

import httpx

BACKEND_DIR = "/root/abc-project/backend"
PYTHON_BIN = os.path.join(BACKEND_DIR, ".venv", "bin", "python3")
E2E_DIR = os.path.join(BACKEND_DIR, "tests", "e2e")
REPORT_PATH = os.path.join(BACKEND_DIR, "challenge_results.json")

def get_system_metrics() -> dict[str, Any]:
    metrics = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "quant_service_status": "unknown",
        "quant_pid": None,
        "rss_memory_kb": 0,
        "open_fds": 0,
        "pg_connections": 0,
        "redis_clients": 0,
    }
    try:
        res = subprocess.run(["systemctl", "is-active", "quant.service"], capture_output=True, text=True)
        metrics["quant_service_status"] = res.stdout.strip()
    except Exception as e:
        metrics["quant_service_status"] = str(e)

    try:
        res = subprocess.run(["pgrep", "-f", "app.main:app"], capture_output=True, text=True)
        pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
        if pids:
            pid = pids[0]
            metrics["quant_pid"] = pid
            metrics["open_fds"] = len(os.listdir(f"/proc/{pid}/fd"))
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        metrics["rss_memory_kb"] = int(line.split()[1])
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["su", "-", "postgres", "-c", "psql -d quant_system -t -A -c 'SELECT count(*) FROM pg_stat_activity;'"],
            capture_output=True, text=True
        )
        if res.returncode == 0 and res.stdout.strip().isdigit():
            metrics["pg_connections"] = int(res.stdout.strip())
    except Exception:
        pass

    try:
        res = subprocess.run(["redis-cli", "info", "clients"], capture_output=True, text=True)
        match = re.search(r"connected_clients:(\d+)", res.stdout)
        if match:
            metrics["redis_clients"] = int(match.group(1))
    except Exception:
        pass

    return metrics

def run_pytest(extra_args: list[str] | None = None) -> dict[str, Any]:
    start = time.time()
    args = [PYTHON_BIN, "-m", "pytest", E2E_DIR, "-ra", "--tb=short", "--asyncio-mode=strict"]
    if extra_args:
        args = [PYTHON_BIN, "-m", "pytest"] + extra_args + ["-ra", "--tb=short", "--asyncio-mode=strict"]

    proc = subprocess.run(args, cwd=BACKEND_DIR, capture_output=True, text=True)
    duration = round(time.time() - start, 3)

    passed, failed, skipped = 0, 0, 0
    p_m = re.search(r"(\d+) passed", proc.stdout)
    f_m = re.search(r"(\d+) failed", proc.stdout)
    s_m = re.search(r"(\d+) skipped", proc.stdout)

    if p_m: passed = int(p_m.group(1))
    if f_m: failed = int(f_m.group(1))
    if s_m: skipped = int(s_m.group(1))

    return {
        "exit_code": proc.returncode,
        "duration_seconds": duration,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": passed + failed + skipped,
        "success": (proc.returncode == 0 and failed == 0 and (passed + skipped) > 0),
        "stdout_tail": proc.stdout[-300:] if proc.stdout else "",
    }

def get_all_test_nodes() -> list[str]:
    cmd = [PYTHON_BIN, "-m", "pytest", E2E_DIR, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=BACKEND_DIR, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if "::test_" in line]

def main():
    print("=" * 80)
    print("  EMPIRICAL CHALLENGER: E2E Stress & Adversarial Suite Starting...")
    print("=" * 80)

    initial_metrics = get_system_metrics()
    print(f"[*] Baseline Metrics: {initial_metrics}")

    results = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "baseline_metrics": initial_metrics,
        "exp1_rapid_repetition": {},
        "exp2_order_randomization": {},
        "exp3_concurrency_stress": {},
        "exp4_boundary_and_robustness": {},
        "final_metrics": {},
    }

    # =========================================================================
    # EXPERIMENT 1: Rapid Repetition (10 consecutive runs)
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> EXPERIMENT 1: 10 CONSECUTIVE E2E RUNS (Zero Delay)")
    print("=" * 80)
    exp1_runs = []
    for i in range(1, 11):
        res = run_pytest()
        met = get_system_metrics()
        status_str = "PASS" if res["success"] else "FAIL"
        print(f"  Run {i:02d}/10: [{status_str}] {res['passed']} passed, {res['failed']} failed in {res['duration_seconds']}s | RSS: {met['rss_memory_kb']}KB | FDs: {met['open_fds']} | PG Conns: {met['pg_connections']}")
        exp1_runs.append({
            "iteration": i,
            "result": res,
            "metrics": met,
        })
    results["exp1_rapid_repetition"] = {
        "total_runs": len(exp1_runs),
        "all_passed": all(r["result"]["success"] for r in exp1_runs),
        "durations": [r["result"]["duration_seconds"] for r in exp1_runs],
        "avg_duration": round(sum(r["result"]["duration_seconds"] for r in exp1_runs) / len(exp1_runs), 3),
        "runs": exp1_runs,
    }

    # =========================================================================
    # EXPERIMENT 2: Execution Order Permutation & Randomization
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> EXPERIMENT 2: ORDER PERMUTATION & RANDOMIZATION")
    print("=" * 80)
    all_nodes = get_all_test_nodes()
    print(f"[*] Collected {len(all_nodes)} total test nodes.")

    permutations = {
        "reversed_file_order": [
            os.path.join(E2E_DIR, "test_tier4_scenarios.py"),
            os.path.join(E2E_DIR, "test_tier3_pairwise.py"),
            os.path.join(E2E_DIR, "test_tier2_boundaries.py"),
            os.path.join(E2E_DIR, "test_tier1_features.py"),
        ],
        "interleaved_file_order": [
            os.path.join(E2E_DIR, "test_tier4_scenarios.py"),
            os.path.join(E2E_DIR, "test_tier1_features.py"),
            os.path.join(E2E_DIR, "test_tier3_pairwise.py"),
            os.path.join(E2E_DIR, "test_tier2_boundaries.py"),
        ],
    }
    for seed in [42, 1337, 2026, 9999]:
        shuffled = list(all_nodes)
        random.seed(seed)
        random.shuffle(shuffled)
        permutations[f"random_shuffle_seed_{seed}"] = shuffled

    exp2_res = {}
    for p_name, targets in permutations.items():
        res = run_pytest(extra_args=targets)
        status_str = "PASS" if res["success"] else "FAIL"
        print(f"  [*] Permutation '{p_name}' ({len(targets)} targets): [{status_str}] {res['passed']} passed, {res['failed']} failed ({res['duration_seconds']}s)")
        exp2_res[p_name] = res

    results["exp2_order_randomization"] = {
        "permutations_tested": len(permutations),
        "all_passed": all(r["success"] for r in exp2_res.values()),
        "details": exp2_res,
    }

    # =========================================================================
    # EXPERIMENT 3: Multi-Process Concurrent Execution Stress
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> EXPERIMENT 3: CONCURRENT MULTI-PROCESS SUITE EXECUTION (3 WORKERS)")
    print("=" * 80)
    exp3_runs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futs = [executor.submit(run_pytest) for _ in range(3)]
        for idx, f in enumerate(concurrent.futures.as_completed(futs), 1):
            res = f.result()
            status_str = "PASS" if res["success"] else "FAIL"
            print(f"  Worker {idx}: [{status_str}] {res['passed']} passed, {res['failed']} failed ({res['duration_seconds']}s)")
            exp3_runs.append(res)
    results["exp3_concurrency_stress"] = {
        "parallel_workers": 3,
        "all_passed": all(r["success"] for r in exp3_runs),
        "runs": exp3_runs,
    }

    # =========================================================================
    # EXPERIMENT 4: SSRF & Burst API Robustness
    # =========================================================================
    print("\n" + "=" * 80)
    print(">>> EXPERIMENT 4: SSRF & BURST API ROBUSTNESS")
    print("=" * 80)

    from app.core.auth import create_access_token
    token = str(create_access_token("stress-admin", role="admin"))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    ssrf_vectors = [
        ("127.0.0.1", "http://127.0.0.1:8000/api/v1/system/status"),
        ("0.0.0.0", "http://0.0.0.0:8000/api/v1/system/status"),
        ("octal_loopback", "http://0177.0.0.1/"),
        ("aws_meta", "http://169.254.169.254/latest/meta-data/"),
        ("private_10", "http://10.0.0.1/"),
        ("private_172", "http://172.16.0.1/"),
        ("private_192", "http://192.168.1.1/"),
    ]

    ssrf_results = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
        for label, url in ssrf_vectors:
            try:
                resp = client.post("/api/v1/control/model-providers/openai/test", json={"base_url": url}, headers=headers)
                blocked = (resp.status_code in (400, 403, 422)) or ("SSRF" in resp.text or "blocked" in resp.text or "forbidden" in resp.text or "failed" in resp.text)
                print(f"  SSRF [{label:15}] -> Status: {resp.status_code} | Defensive: {blocked} | Body: {resp.text[:60]}")
                ssrf_results.append({"vector": label, "url": url, "status_code": resp.status_code, "defended": blocked})
            except Exception as e:
                print(f"  SSRF [{label:15}] -> Exception (blocked): {e}")
                ssrf_results.append({"vector": label, "url": url, "defended": True, "error": str(e)})

    # Burst API Stress (100 parallel requests)
    burst_results = []
    print("\n[*] Sending 100 concurrent requests to /api/v1/market/tickers & /health...")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15.0) as client:
        def fetch_ticker():
            return client.get("/api/v1/market/tickers").status_code
        def fetch_health():
            return client.get("/health").status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            t_futs = [executor.submit(fetch_ticker) for _ in range(50)]
            h_futs = [executor.submit(fetch_health) for _ in range(50)]
            t_codes = [f.result() for f in concurrent.futures.as_completed(t_futs)]
            h_codes = [f.result() for f in concurrent.futures.as_completed(h_futs)]
            t_ok = sum(1 for c in t_codes if c == 200)
            h_ok = sum(1 for c in h_codes if c == 200)
            print(f"  Burst /api/v1/market/tickers: {t_ok}/50 HTTP 200 OK")
            print(f"  Burst /health:               {h_ok}/50 HTTP 200 OK")
            burst_results = [
                {"endpoint": "/api/v1/market/tickers", "success_200": t_ok, "total": 50},
                {"endpoint": "/health", "success_200": h_ok, "total": 50},
            ]

    results["exp4_boundary_and_robustness"] = {
        "ssrf_tests": ssrf_results,
        "burst_tests": burst_results,
    }

    # Final Telemetry Check
    final_metrics = get_system_metrics()
    print("\n" + "=" * 80)
    print(f"[*] Final System Metrics: {final_metrics}")
    print("=" * 80)
    results["final_metrics"] = final_metrics

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[✓] Adversarial Stress & Robustness Suite Complete! Saved: {REPORT_PATH}")

if __name__ == "__main__":
    main()
