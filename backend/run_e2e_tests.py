#!/usr/bin/env python3
"""Enterprise AI Quant System - 4-Tier E2E Test Suite Runner & Report Generator.

Executes Tier 1 (Feature Coverage), Tier 2 (Boundary & Corner Cases),
Tier 3 (Pairwise Integrations), and Tier 4 (Real-World Business Scenarios).
Generates structured JSON report at /root/abc-project/backend/e2e_test_report.json.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
from typing import Any

import pytest

# Ensure backend root is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


class E2ETestResultCollector:
    """Pytest plugin to collect detailed test results by Tier."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def pytest_sessionstart(self, session):
        self.start_time = time.time()

    def pytest_sessionfinish(self, session, exitstatus):
        self.end_time = time.time()

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.skipped):
            tier = "Unknown"
            file_name = os.path.basename(report.fspath)
            if "tier1" in file_name:
                tier = "Tier 1: Feature Coverage"
            elif "tier2" in file_name:
                tier = "Tier 2: Boundary & Corner Cases"
            elif "tier3" in file_name:
                tier = "Tier 3: Pairwise Combinations"
            elif "tier4" in file_name:
                tier = "Tier 4: Real-World Scenarios"

            outcome = "PASSED" if report.passed else ("SKIPPED" if report.skipped else "FAILED")
            err_msg = str(report.longrepr) if report.failed else None

            self.results.append({
                "node_id": report.nodeid,
                "name": report.location[2] if len(report.location) > 2 else report.nodeid,
                "file": file_name,
                "tier": tier,
                "outcome": outcome,
                "duration_seconds": round(report.duration, 4),
                "error": err_msg,
            })


def run_e2e_suite() -> int:
    """Run all E2E tests and output structured JSON report."""
    test_dir = os.path.join(backend_dir, "tests", "e2e")
    collector = E2ETestResultCollector()

    print("=" * 80)
    print("  Enterprise AI Quant System (v0.2.0) — 4-Tier E2E Test Suite Runner")
    print(f"  Target Test Directory: {test_dir}")
    print(f"  Execution Timestamp:   {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    pytest_args = [
        test_dir,
        "-v",
        "-ra",
        "--tb=short",
        "--asyncio-mode=strict",
    ]

    exit_code = pytest.main(pytest_args, plugins=[collector])

    # Aggregate metrics
    total_tests = len(collector.results)
    passed_tests = sum(1 for r in collector.results if r["outcome"] == "PASSED")
    failed_tests = sum(1 for r in collector.results if r["outcome"] == "FAILED")
    skipped_tests = sum(1 for r in collector.results if r["outcome"] == "SKIPPED")
    total_duration = round(collector.end_time - collector.start_time, 3)

    tiers_data: dict[str, dict[str, Any]] = {
        "Tier 1: Feature Coverage": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "tests": []},
        "Tier 2: Boundary & Corner Cases": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "tests": []},
        "Tier 3: Pairwise Combinations": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "tests": []},
        "Tier 4: Real-World Scenarios": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "tests": []},
    }

    for res in collector.results:
        t_key = res["tier"]
        if t_key not in tiers_data:
            tiers_data[t_key] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "tests": []}
        tiers_data[t_key]["total"] += 1
        if res["outcome"] == "PASSED":
            tiers_data[t_key]["passed"] += 1
        elif res["outcome"] == "FAILED":
            tiers_data[t_key]["failed"] += 1
        elif res["outcome"] == "SKIPPED":
            tiers_data[t_key]["skipped"] += 1
        tiers_data[t_key]["duration"] = round(tiers_data[t_key]["duration"] + res["duration_seconds"], 4)
        tiers_data[t_key]["tests"].append(res)

    pass_rate = round((passed_tests / total_tests * 100.0) if total_tests > 0 else 0.0, 2)

    report_payload = {
        "title": "Enterprise AI Quant System - 4-Tier E2E Test Report",
        "version": "0.2.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "summary": {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "skipped": skipped_tests,
            "pass_rate_percent": pass_rate,
            "total_duration_seconds": total_duration,
            "status": "PASSED" if failed_tests == 0 and total_tests > 0 else "FAILED",
        },
        "tiers": tiers_data,
    }

    report_path = os.path.join(backend_dir, "e2e_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("  4-Tier E2E Test Execution Summary")
    print("=" * 80)
    for t_name, t_info in tiers_data.items():
        print(f"  [{'✓' if t_info['failed'] == 0 and t_info['total'] > 0 else '✗'}] {t_name:34} | Total: {t_info['total']:3} | Passed: {t_info['passed']:3} | Failed: {t_info['failed']:2} | Time: {t_info['duration']:6.2f}s")
    print("-" * 80)
    print(f"  TOTAL: {total_tests} Tests | PASSED: {passed_tests} | FAILED: {failed_tests} | SKIPPED: {skipped_tests} | PASS RATE: {pass_rate}%")
    print(f"  Duration: {total_duration:.2f}s | Report Artifact: {report_path}")
    print("=" * 80 + "\n")

    return 0 if failed_tests == 0 and total_tests > 0 else 1


if __name__ == "__main__":
    sys.exit(run_e2e_suite())
