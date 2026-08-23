from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import numpy as np

from app.evaluator import EvalCaseResult, calculate_metrics, evaluate_case, load_evaluation_dataset
from main import app

client = TestClient(app)


def _latency_percentiles(latencies: list[float]) -> dict[str, float]:
    return {
        "p50": round(float(np.percentile(latencies, 50)), 2),
        "p90": round(float(np.percentile(latencies, 90)), 2),
        "p95": round(float(np.percentile(latencies, 95)), 2),
        "p99": round(float(np.percentile(latencies, 99)), 2),
        "mean": round(float(np.mean(latencies)), 2),
        "min": min(latencies),
        "max": max(latencies),
    }


def _run_all_cases(dataset: list[dict[str, Any]], label: str) -> tuple[list[EvalCaseResult], list[float]]:
    case_results = []
    latencies = []
    for i, case in enumerate(dataset, 1):
        cid = case["id"]
        cat = case["category"]
        print(f"  [{label}] [{i:02d}/{len(dataset)}] Running {cid} ({cat})...", end=" ", flush=True)
        t0 = time.perf_counter()
        res = evaluate_case(case, client)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        latencies.append(latency_ms)
        case_results.append(res)
        if res.is_inference_error:
            status_str = "INFRA-ERROR"
        else:
            status_str = "PASSED" if res.case_pass else "FAILED"
        print(f"{status_str} [fact_acc={res.fact_accuracy * 100:.0f}%] ({latency_ms} ms)")
    return case_results, latencies


def _failures_detail(dataset: list[dict[str, Any]], case_results: list[EvalCaseResult]) -> list[dict[str, Any]]:
    dataset_by_id = {c["id"]: c for c in dataset}
    failures_detail = []
    for r in case_results:
        if not r.case_pass:
            expected_meta = dataset_by_id[r.case_id]["expected"]
            failures_detail.append({
                "case_id": r.case_id,
                "category": r.category,
                "query": r.query,
                "is_inference_error": r.is_inference_error,
                "fact_accuracy": r.fact_accuracy,
                "failure_reasons": r.failure_reasons,
                "expected": {
                    "outcome": expected_meta.get("outcome"),
                    "required_facts": expected_meta.get("required_facts"),
                    "required_sources": expected_meta.get("required_sources"),
                    "forbidden_sources": expected_meta.get("forbidden_sources"),
                },
                "actual": {
                    "status_code": r.status_code,
                    "answer": r.raw_answer,
                    "confidence": r.confidence,
                    "sources": r.sources,
                    "facts_matched": r.facts_matched,
                    "facts_missed": r.facts_missed,
                },
            })
    return failures_detail


def _all_cases_detail(case_results: list[EvalCaseResult], latencies: list[float]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": r.case_id,
            "category": r.category,
            "query": r.query,
            "case_pass": r.case_pass,
            "is_inference_error": r.is_inference_error,
            "fact_accuracy": r.fact_accuracy,
            "latency_ms": lat,
            "status_code": r.status_code,
            "answer": r.raw_answer,
            "confidence": r.confidence,
            "sources": r.sources,
            "facts_matched": r.facts_matched,
            "facts_missed": r.facts_missed,
            "is_leakage": r.is_leakage,
            "is_unsafe_action": r.is_unsafe_action,
            "applied_correct_override": r.applied_correct_override,
            "forbidden_sources_found": r.forbidden_sources_found,
            "failure_reasons": r.failure_reasons,
        }
        for r, lat in zip(case_results, latencies)
    ]


def run_single(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    """The original one-shot benchmark: unchanged output shape, unchanged file."""
    print(f"Running evaluation through live Medha endpoint...\n")

    case_results, latencies = _run_all_cases(dataset, "run")

    lat = _latency_percentiles(latencies)
    metrics = calculate_metrics(case_results, dataset)
    failures_detail = _failures_detail(dataset, case_results)

    output_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": metrics.total_cases,
        "case_pass_count": sum(1 for r in case_results if r.case_pass),
        "case_pass_rate": metrics.case_pass_rate,
        "overall_fact_accuracy": metrics.fact_accuracy,
        "latencies_ms": {
            "p50": lat["p50"], "p90": lat["p90"], "p95": lat["p95"], "p99": lat["p99"],
            "mean": lat["mean"], "min": lat["min"], "max": lat["max"],
        },
        "overall_metrics": {
            "fact_accuracy": metrics.fact_accuracy,
            "case_pass_rate": metrics.case_pass_rate,
            "hit_at_1": metrics.hit_at_1,
            "hit_at_3": metrics.hit_at_3,
            "hit_at_5": metrics.hit_at_5,
            "citation_precision": metrics.citation_precision,
            "citation_completeness": metrics.citation_completeness,
            "contract_override_accuracy": metrics.contract_override_accuracy,
            "tenant_leakage_rate": metrics.tenant_leakage_rate,
            "unsafe_action_rate": metrics.unsafe_action_rate,
            "abstention_recall": metrics.abstention_recall,
            "over_abstention_rate": metrics.over_abstention_rate,
            "acceptance_passed": metrics.acceptance_passed,
        },
        "category_metrics": metrics.category_metrics,
        "failed_case_ids": metrics.failed_case_ids,
        "inference_error_case_ids": [r.case_id for r in case_results if r.is_inference_error],
        "failures_detail": failures_detail,
        "all_cases": _all_cases_detail(case_results, latencies),
    }

    results_path = Path(__file__).parent.parent / "evaluation_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n=======================================================")
    print(f"Evaluation Results Summary")
    print(f"=======================================================")
    print(f"Total Cases:         {metrics.total_cases}")
    print(f"Overall Fact Acc:    {metrics.fact_accuracy * 100:.1f}%")
    print(f"Case Pass Rate:      {metrics.case_pass_rate * 100:.1f}% ({sum(1 for r in case_results if r.case_pass)}/{metrics.total_cases})")
    print(f"Latency (ms):        p50 = {lat['p50']:.1f}ms, p95 = {lat['p95']:.1f}ms")
    print(f"Failed Case IDs:     {metrics.failed_case_ids}")
    print(f"Saved report to:     {results_path}")

    return output_data


def run_stability(dataset: list[dict[str, Any]], runs: int) -> dict[str, Any]:
    """Execute all 28 live cases `runs` times independently and report stability."""
    all_case_ids = [c["id"] for c in dataset]
    run_reports: list[dict[str, Any]] = []
    pooled_latencies: list[float] = []
    pass_by_case: dict[str, int] = {cid: 0 for cid in all_case_ids}

    tenant_leakage_count = 0
    unsafe_action_count = 0
    contract_override_violation_count = 0
    citation_precision_violation_count = 0
    inference_error_total = 0

    for run_idx in range(1, runs + 1):
        print(f"\n=== Run {run_idx}/{runs} ===")
        case_results, latencies = _run_all_cases(dataset, f"run {run_idx}")
        pooled_latencies.extend(latencies)

        metrics = calculate_metrics(case_results, dataset)
        lat = _latency_percentiles(latencies)
        inference_error_ids = [r.case_id for r in case_results if r.is_inference_error]

        for r in case_results:
            if r.case_pass:
                pass_by_case[r.case_id] += 1
            if r.is_leakage:
                tenant_leakage_count += 1
            if r.is_unsafe_action:
                unsafe_action_count += 1
            if r.category in {"contract_override", "contract_sla", "paraphrase"} and not r.applied_correct_override:
                contract_override_violation_count += 1
            if r.forbidden_sources_found:
                citation_precision_violation_count += 1
            if r.is_inference_error:
                inference_error_total += 1

        run_reports.append({
            "run": run_idx,
            "passed_cases": sum(1 for r in case_results if r.case_pass),
            "total_cases": metrics.total_cases,
            "pass_rate": metrics.case_pass_rate,
            "failed_case_ids": metrics.failed_case_ids,
            "inference_error_case_ids": inference_error_ids,
            "fact_accuracy": metrics.fact_accuracy,
            "hit_at_3": metrics.hit_at_3,
            "hit_at_5": metrics.hit_at_5,
            "citation_precision": metrics.citation_precision,
            "citation_completeness": metrics.citation_completeness,
            "contract_override_accuracy": metrics.contract_override_accuracy,
            "tenant_leakage_rate": metrics.tenant_leakage_rate,
            "unsafe_action_rate": metrics.unsafe_action_rate,
            "abstention_recall": metrics.abstention_recall,
            "over_abstention_rate": metrics.over_abstention_rate,
            "latencies_ms": lat,
            "cases": _all_cases_detail(case_results, latencies),
        })

    pass_rates = [r["pass_rate"] for r in run_reports]
    mean_pass_rate = round(float(np.mean(pass_rates)), 4)
    min_pass_rate = round(min(pass_rates), 4)
    max_pass_rate = round(max(pass_rates), 4)
    aggregate_latency = _latency_percentiles(pooled_latencies)

    per_case_pass_frequency = {cid: {"passed": pass_by_case[cid], "of": runs} for cid in all_case_ids}
    repeated_failures = {cid: f"{runs - v['passed']}/{runs}" for cid, v in per_case_pass_frequency.items() if v["passed"] < runs}

    stability_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": runs,
        "total_cases": len(all_case_ids),
        "run_reports": run_reports,
        "mean_case_pass_rate": mean_pass_rate,
        "min_case_pass_rate": min_pass_rate,
        "max_case_pass_rate": max_pass_rate,
        "per_case_pass_frequency": per_case_pass_frequency,
        "repeated_failures": repeated_failures,
        "safety_across_all_runs": {
            "tenant_leakage": tenant_leakage_count,
            "unsafe_actions": unsafe_action_count,
            "contract_override_violations": contract_override_violation_count,
            "citation_precision_violations": citation_precision_violation_count,
        },
        "inference_errors_total": inference_error_total,
        "aggregate_latency_ms": aggregate_latency,
    }

    results_path = Path(__file__).parent.parent / "evaluation_stability_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(stability_report, f, indent=2)

    _print_stability_summary(stability_report, results_path)
    return stability_report


def _print_stability_summary(report: dict[str, Any], results_path: Path) -> None:
    print(f"\n=======================================================")
    print(f"Stability Summary ({report['runs']} runs)")
    print(f"=======================================================")
    for r in report["run_reports"]:
        failures = ", ".join(r["failed_case_ids"]) if r["failed_case_ids"] else "none"
        line = f"Run {r['run']}: {r['passed_cases']}/{r['total_cases']} — failures: {failures}"
        if r["inference_error_case_ids"]:
            line += f" | inference errors: {', '.join(r['inference_error_case_ids'])}"
        print(line)

    print("\nRepeated failures:")
    if report["repeated_failures"]:
        for cid, frac in report["repeated_failures"].items():
            print(f"{cid}: {frac}")
    else:
        print("none")

    safety = report["safety_across_all_runs"]
    print("\nSafety across all runs:")
    print(f"tenant leakage: {safety['tenant_leakage']}")
    print(f"unsafe actions: {safety['unsafe_actions']}")
    print(f"contract override violations: {safety['contract_override_violations']}")
    print(f"citation precision violations: {safety['citation_precision_violations']}")

    if report["inference_errors_total"]:
        print(f"\nInference/runtime errors (HTTP 503, excluded from semantic scoring): {report['inference_errors_total']}")

    print(f"\nMean case pass rate: {report['mean_case_pass_rate'] * 100:.1f}%")
    print(f"Min/Max case pass rate: {report['min_case_pass_rate'] * 100:.1f}% / {report['max_case_pass_rate'] * 100:.1f}%")

    print("\nPer-case pass frequency (not always passing):")
    imperfect = {cid: v for cid, v in report["per_case_pass_frequency"].items() if v["passed"] < report["runs"]}
    if imperfect:
        for cid, v in imperfect.items():
            print(f"{cid}: {v['passed']}/{v['of']}")
    else:
        print("none — all cases passed every run")

    agg = report["aggregate_latency_ms"]
    print(f"\nAggregate latency: p50 = {agg['p50']:.1f}ms, p95 = {agg['p95']:.1f}ms")
    print(f"Saved report to: {results_path}")


def main():
    parser = argparse.ArgumentParser(description="Run ParcelPilot's live 28-case evaluation benchmark.")
    parser.add_argument("--runs", type=int, default=1, help="Number of independent full benchmark passes (default: 1).")
    args = parser.parse_args()

    dataset_path = Path(__file__).parent.parent / "data" / "evaluation_dataset.json"
    dataset = load_evaluation_dataset(dataset_path)
    print(f"Loaded {len(dataset)} evaluation cases from {dataset_path.name}")

    if args.runs <= 1:
        run_single(dataset)
    else:
        run_stability(dataset, args.runs)


if __name__ == "__main__":
    main()
