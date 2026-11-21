"""Evaluation harness for measuring Tier A/B precision, recall, and latency.

Evaluates crime scene analysis performance against ground-truth fixture expectations.
Supports dry-run, stub-replayed, and live LLM evaluation modes.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any

import dotenv

dotenv.load_dotenv(dotenv_path=Path.cwd() / ".env")

from src.analysis.pipeline import run_pipeline
from src.llm import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    PERMITTED_TIER_B_TYPES,
    groq_rate_limiter,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
CHECKPOINTS_DIR = REPORTS_DIR / "checkpoints"
ACTIVE_CHECKPOINT_FILE = CHECKPOINTS_DIR / "eval_checkpoint_active.json"

# Acceptance targets defined in PROJECT_BRIEF.md §11
ACCEPTANCE_TARGETS = {
    "tier_a_recall": {"target": 1.00, "op": "==", "display": "1.00", "required": True},
    "tier_a_precision": {"target": None, "op": "info", "display": "Informational", "required": False},
    "tier_b_recall": {"target": 0.85, "op": ">=", "display": "≥0.85", "required": True},
    "tier_b_precision": {"target": 0.85, "op": ">=", "display": "≥0.85", "required": True},
    "hallucination_rate": {"target": 0.00, "op": "==", "display": "0.00", "required": True},
    "clean_cases_fp": {"target": 0, "op": "==", "display": "0", "required": True},
    "median_latency_ms": {"target": 6000.0, "op": "<", "display": "<6000 ms", "required": True},
}


# --- Checkpoint Management ---

def compute_fixture_fingerprint(fixtures: list[tuple[str, Path, Path]]) -> str:
    """Compute sha256 fingerprint of all discovered fixtures and expected results."""
    h = hashlib.sha256()
    for stem, case_p, exp_p in fixtures:
        h.update(stem.encode("utf-8"))
        h.update(case_p.read_bytes())
        h.update(exp_p.read_bytes())
    return h.hexdigest()


def save_checkpoint(checkpoint_data: dict[str, Any], path: Path = ACTIVE_CHECKPOINT_FILE) -> None:
    """Save evaluation checkpoint atomically to prevent corruption on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(checkpoint_data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def load_checkpoint(path: Path = ACTIVE_CHECKPOINT_FILE) -> dict[str, Any] | None:
    """Load active checkpoint if it exists and is valid JSON."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --- Evaluation Client (Dry-Run / Stub / Live Wrapper) ---

class EvaluationLLMClient(LLMClient):
    """Evaluation client supporting dry-run, stub replay, and live execution."""

    def __init__(
        self,
        mode: str = "dry_run",
        stub_responses: dict[str, Any] | None = None,
        live_client: LLMClient | None = None,
    ) -> None:
        self.mode = mode
        self.stub_responses = stub_responses or {}
        self.live_client = live_client
        self.rate_limited_count = 0

    def analyze_case(
        self,
        case_context: dict[str, Any],
        assigned_analysis_type: str,
    ) -> LLMResponse:
        case_id = str(case_context.get("case", {}).get("id", "UNKNOWN"))

        if self.mode == "dry_run":
            return LLMResponse({
                "suggestions": [],
                "status": "success",
                "error": None,
                "raw_response": '{"suggestions": []}',
                "provider": "dry_run",
                "model": "dry_run",
                "attempts": 1,
                "latency_ms": 0.0,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        if self.mode == "stub":
            # Support both fixture stem lookup and case ID lookup
            candidate_keys = [
                f"{case_id}:{assigned_analysis_type}",
            ]
            # If context has a custom stem or file reference, try it
            fixture_stem = case_context.get("_fixture_stem")
            if fixture_stem:
                candidate_keys.insert(0, f"{fixture_stem}:{assigned_analysis_type}")

            matched_key = None
            for key in candidate_keys:
                if key in self.stub_responses:
                    matched_key = key
                    break

            if matched_key is None:
                raise KeyError(
                    f"Missing stub response for '{candidate_keys[0]}' in stub responses file."
                )

            raw_data = self.stub_responses[matched_key]
            if not isinstance(raw_data, dict):
                raise ValueError(
                    f"Stub response for '{matched_key}' must be a JSON object, got {type(raw_data).__name__}"
                )

            return LLMResponse({
                "suggestions": raw_data.get("suggestions", []),
                "status": "success",
                "error": None,
                "raw_response": json.dumps(raw_data),
                "provider": "stub",
                "model": "stub",
                "attempts": 1,
                "latency_ms": 0.0,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        if self.mode == "live":
            if self.live_client is None:
                raise RuntimeError("Live client not configured for live evaluation mode.")
            return self.live_client.analyze_case(case_context, assigned_analysis_type)

        raise ValueError(f"Unknown evaluation mode: {self.mode}")


# --- Fixture Discovery ---

def natural_sort_key(s: str) -> list[Any]:
    """Sort strings containing numbers in human-natural order (e.g. C2 before C10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def discover_fixtures(cases_dir: Path) -> list[tuple[str, Path, Path]]:
    """Dynamically discover case fixtures that possess a corresponding .expected.json file.

    Returns:
        Sorted list of tuples: (fixture_stem, case_json_path, expected_json_path)
    """
    if not cases_dir.is_dir():
        return []

    discovered: list[tuple[str, Path, Path]] = []
    for file_path in cases_dir.glob("*.json"):
        if file_path.name.endswith(".expected.json"):
            continue
        expected_path = file_path.with_name(f"{file_path.stem}.expected.json")
        if expected_path.is_file():
            discovered.append((file_path.stem, file_path, expected_path))

    discovered.sort(key=lambda item: natural_sort_key(item[0]))
    return discovered


# --- Metrics Calculation and Matching ---

def match_tier_a(
    expected_tier_a: list[dict[str, Any]],
    produced_flags: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare Tier A produced flags against expected (rule, about_ref) items.

    Each produced flag entry matches an expected entry if both rule and ref match.
    Each item can match at most once.
    """
    expected_pairs: list[tuple[str, str]] = []
    for exp in expected_tier_a:
        expected_pairs.append((str(exp.get("rule", "")), str(exp.get("about_ref", ""))))

    produced_pairs: list[tuple[str, str]] = []
    for flag in produced_flags:
        rule = str(flag.get("rule", ""))
        for ref in flag.get("evidence_refs", []):
            produced_pairs.append((rule, str(ref)))

    unmatched_expected = list(expected_pairs)
    unmatched_produced = list(produced_pairs)
    matched_count = 0

    for exp in list(unmatched_expected):
        if exp in unmatched_produced:
            matched_count += 1
            unmatched_expected.remove(exp)
            unmatched_produced.remove(exp)

    tp = matched_count
    fn = len(unmatched_expected)
    fp = len(unmatched_produced)

    recall = (tp / (tp + fn)) if (tp + fn) > 0 else None
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else None

    return {
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "recall": recall,
        "precision": precision,
        "expected_count": len(expected_pairs),
        "produced_count": len(produced_pairs),
    }


def match_tier_b(
    expected_tier_b: list[dict[str, Any]],
    validated_suggestions: list[dict[str, Any]],
    is_clean: bool,
) -> dict[str, Any]:
    """Compare Tier B validated suggestions against expected findings.

    An expected entry matches a validated suggestion if:
    - analysis type matches
    - cited reference set matches about_refs set order-insensitively
    Each produced suggestion can match at most once.
    Soft expected entries: missed soft is not an FN; matched soft is a bonus hit (not FP).
    For clean cases, any validated suggestion is an FP.
    """
    matched_expected_indices: set[int] = set()
    matched_produced_indices: set[int] = set()
    bonus_hits = 0

    for p_idx, p_sug in enumerate(validated_suggestions):
        p_type = p_sug.get("type")
        p_refs = set(p_sug.get("evidence_refs", []))

        for e_idx, e_exp in enumerate(expected_tier_b):
            if e_idx in matched_expected_indices:
                continue
            e_type = e_exp.get("type")
            e_refs = set(e_exp.get("about_refs", []))

            if p_type == e_type and p_refs == e_refs:
                matched_produced_indices.add(p_idx)
                matched_expected_indices.add(e_idx)
                if e_exp.get("soft", False):
                    bonus_hits += 1
                break

    # Hard expected items
    hard_expected = [e for e in expected_tier_b if not e.get("soft", False)]
    hard_matched = [
        e for idx, e in enumerate(expected_tier_b)
        if idx in matched_expected_indices and not e.get("soft", False)
    ]

    tp = len(hard_matched)
    fn = len(hard_expected) - len(hard_matched)
    fp = len(validated_suggestions) - len(matched_produced_indices)

    recall = (tp / (tp + fn)) if (tp + fn) > 0 else None
    precision = ((tp + bonus_hits) / len(validated_suggestions)) if len(validated_suggestions) > 0 else None

    return {
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "bonus_hits": bonus_hits,
        "recall": recall,
        "precision": precision,
        "expected_hard_count": len(hard_expected),
        "expected_total_count": len(expected_tier_b),
        "validated_count": len(validated_suggestions),
    }


# --- Evaluation Engine ---

def evaluate_case(
    fixture_stem: str,
    case_path: Path,
    expected_path: Path,
    client: EvaluationLLMClient,
    in_progress_categories: dict[str, Any] | None = None,
    on_category_complete: Any | None = None,
) -> dict[str, Any]:
    """Execute evaluation for a single case fixture with category-level checkpointing."""
    case_data = json.loads(case_path.read_text(encoding="utf-8"))
    expected_data = json.loads(expected_path.read_text(encoding="utf-8"))

    # Attach fixture stem to context for stub lookup
    case_data["_fixture_stem"] = fixture_stem

    is_clean = bool(expected_data.get("clean", False))
    expected_tier_a = expected_data.get("tier_a_expected", [])
    expected_tier_b = expected_data.get("tier_b_expected", [])

    # Determine Tier B categories to execute
    if expected_tier_b:
        categories_to_run = sorted(list({entry["type"] for entry in expected_tier_b if "type" in entry}))
    else:
        # If tier_b_expected is empty, run all 3 categories to measure false positives
        categories_to_run = sorted(list(PERMITTED_TIER_B_TYPES))

    tier_a_flags: list[dict[str, Any]] = []
    validated_suggestions: list[dict[str, Any]] = []
    rejected_suggestions: list[dict[str, Any]] = []
    drop_reasons: dict[str, int] = {
        "schema_fail": 0,
        "type_mismatch": 0,
        "unresolved_ref": 0,
        "dismissal_guard": 0,
        "hallucination_suspected": 0,
        "deduped_by_tier_a": 0,
    }
    total_received = 0
    total_rejected = 0
    provider_latencies: list[float] = []
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    errors: list[str] = []

    case_start_time = time.perf_counter()

    for idx, category in enumerate(categories_to_run):
        # 1. Check if category already completed in checkpoint
        if in_progress_categories and category in in_progress_categories:
            cached = in_progress_categories[category]
            if idx == 0 and "tier_a_flags" in cached:
                tier_a_flags = cached["tier_a_flags"]

            validated_suggestions.extend(cached.get("tier_b_suggestions", []))
            rejected_suggestions.extend(cached.get("rejected_suggestions", []))

            c_stats = cached.get("stats", {})
            total_received += c_stats.get("received", 0)
            total_rejected += c_stats.get("rejected", 0)
            for k, v in c_stats.get("drop_reasons", {}).items():
                drop_reasons[k] += v

            tokens["prompt_tokens"] += cached.get("tokens", {}).get("prompt_tokens", 0)
            tokens["completion_tokens"] += cached.get("tokens", {}).get("completion_tokens", 0)
            tokens["total_tokens"] += cached.get("tokens", {}).get("total_tokens", 0)

            if "inv_latency" in cached:
                provider_latencies.append(cached["inv_latency"])
            continue

        # 2. Execute pipeline for category
        try:
            res = run_pipeline(
                case_context=case_data,
                client=client,
                tier_b_types=[category],
                write_audit=False,
            )

            # Collect Tier A flags only once per case
            if idx == 0:
                tier_a_flags = res.tier_a_flags

            validated_suggestions.extend(res.tier_b_suggestions)
            rejected_suggestions.extend(res.rejected_suggestions)

            val_stats = res.stats
            total_received += val_stats.get("received", 0)
            total_rejected += val_stats.get("rejected", 0)
            for k, v in val_stats.get("drop_reasons", {}).items():
                drop_reasons[k] += v

            cat_tokens = {
                "prompt_tokens": val_stats.get("total_prompt_tokens", 0),
                "completion_tokens": val_stats.get("total_completion_tokens", 0),
                "total_tokens": val_stats.get("total_tokens", 0),
            }
            tokens["prompt_tokens"] += cat_tokens["prompt_tokens"]
            tokens["completion_tokens"] += cat_tokens["completion_tokens"]
            tokens["total_tokens"] += cat_tokens["total_tokens"]

            inv_latency = val_stats.get("total_latency_ms", 0.0)
            provider_latencies.append(inv_latency)

            # Check for rate-limiting in invocation outcomes
            for outcome in res.invocation_outcomes:
                if (
                    outcome.get("status") == "error"
                    and (
                        outcome.get("error_type") == "LLMRateLimitError"
                        or "429" in str(outcome.get("error", ""))
                    )
                ):
                    client.rate_limited_count += 1

            cat_data = {
                "tier_b_suggestions": res.tier_b_suggestions,
                "rejected_suggestions": res.rejected_suggestions,
                "stats": val_stats,
                "invocation_outcomes": res.invocation_outcomes,
                "tokens": cat_tokens,
                "inv_latency": inv_latency,
            }
            if idx == 0:
                cat_data["tier_a_flags"] = res.tier_a_flags

            if on_category_complete:
                on_category_complete(fixture_stem, category, cat_data)

        except Exception as exc:
            errors.append(f"Pipeline error on {fixture_stem} [{category}]: {exc}")

    case_wall_clock_ms = round((time.perf_counter() - case_start_time) * 1000, 2)

    # Matching
    tier_a_match = match_tier_a(expected_tier_a, tier_a_flags)
    tier_b_match = match_tier_b(expected_tier_b, validated_suggestions, is_clean)

    # Exactly one latency measurement per case (end-to-end wall-clock time in live mode)
    case_latency = case_wall_clock_ms if client.mode == "live" else None

    return {
        "fixture_stem": fixture_stem,
        "case_id": case_data.get("case", {}).get("id", fixture_stem),
        "clean": is_clean,
        "categories_run": categories_to_run,
        "tier_a": tier_a_match,
        "tier_b": tier_b_match,
        "rejections": {
            "received": total_received,
            "rejected": total_rejected,
            "drop_reasons": drop_reasons,
        },
        "latency_ms": case_latency,
        "diagnostic_provider_latencies_ms": provider_latencies,
        "tokens": tokens,
        "errors": errors,
    }


def evaluate_all(
    cases_dir: Path,
    mode: str = "dry_run",
    stub_path: Path | None = None,
    max_concurrency: int = 2,
    live_config: LLMConfig | None = None,
    reset_checkpoint: bool = False,
    use_checkpoint: bool | None = None,
) -> dict[str, Any]:
    """Execute complete evaluation harness across all discoverable fixtures with checkpointing."""
    fixtures = discover_fixtures(cases_dir)
    if not fixtures:
        raise FileNotFoundError(f"No case fixtures with .expected.json found in {cases_dir}")

    stub_responses: dict[str, Any] = {}
    if mode == "stub":
        if not stub_path or not stub_path.is_file():
            raise FileNotFoundError(f"Stub responses file not found: {stub_path}")
        stub_responses = json.loads(stub_path.read_text(encoding="utf-8"))

    live_client: LLMClient | None = None
    if mode == "live":
        live_client = LLMClient(config=live_config or LLMConfig())

    client = EvaluationLLMClient(
        mode=mode,
        stub_responses=stub_responses,
        live_client=live_client,
    )

    if use_checkpoint is None:
        use_checkpoint = (mode == "live")

    active_cp: dict[str, Any] = {}
    completed_fixtures: dict[str, Any] = {}
    in_progress_categories: dict[str, Any] = {}
    resumption_count = 0
    benchmark_start_time = time.time()
    initial_cooldown_wait_s = 0.0

    if use_checkpoint:
        CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        if reset_checkpoint and ACTIVE_CHECKPOINT_FILE.exists():
            ACTIVE_CHECKPOINT_FILE.unlink()
            print("[CHECKPOINT] Reset active checkpoint. Starting fresh.")

        existing_cp = load_checkpoint(ACTIVE_CHECKPOINT_FILE)
        provider_name = getattr(live_client.config, "provider", "") if live_client else mode
        model_name = getattr(live_client.config, "model", "") if live_client else mode
        current_meta = {
            "provider": provider_name,
            "model": model_name,
            "mode": mode,
            "fixture_stems": [stem for stem, _, _ in fixtures],
            "fixture_fingerprint": compute_fixture_fingerprint(fixtures),
        }

        if existing_cp:
            cp_meta = existing_cp.get("config_metadata", {})
            if (
                cp_meta.get("provider") != current_meta["provider"]
                or cp_meta.get("model") != current_meta["model"]
                or cp_meta.get("mode") != current_meta["mode"]
                or cp_meta.get("fixture_fingerprint") != current_meta["fixture_fingerprint"]
            ):
                raise RuntimeError(
                    f"Checkpoint configuration mismatch: active checkpoint is configured for "
                    f"'{cp_meta.get('provider')}/{cp_meta.get('model')}' with fingerprint {cp_meta.get('fixture_fingerprint', '')[:8]}..., "
                    f"but current execution is configured for '{current_meta['provider']}/{current_meta['model']}' "
                    f"with fingerprint {current_meta['fixture_fingerprint'][:8]}.... "
                    f"Run with --reset-checkpoint to discard previous checkpoint."
                )
            active_cp = existing_cp
            completed_fixtures = active_cp.get("completed_fixtures", {})
            in_progress_categories = active_cp.get("in_progress_categories", {})
            resumption_count = active_cp.get("resumption_count", 0) + 1
            benchmark_start_time = active_cp.get("benchmark_start_time", benchmark_start_time)
            initial_cooldown_wait_s = active_cp.get("total_cooldown_wait_s", 0.0)
            active_cp["resumption_count"] = resumption_count
            save_checkpoint(active_cp, ACTIVE_CHECKPOINT_FILE)
            print(f"[CHECKPOINT] Resuming evaluation session #{resumption_count}: {len(completed_fixtures)}/{len(fixtures)} fixtures completed.")
        else:
            active_cp = {
                "version": 1,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "config_metadata": current_meta,
                "benchmark_start_time": benchmark_start_time,
                "resumption_count": 0,
                "total_cooldown_wait_s": 0.0,
                "completed_fixtures": {},
                "in_progress_categories": {},
            }
            save_checkpoint(active_cp, ACTIVE_CHECKPOINT_FILE)

    def on_category_complete(stem: str, cat: str, cat_data: dict[str, Any]) -> None:
        if not use_checkpoint:
            return
        if "in_progress_categories" not in active_cp:
            active_cp["in_progress_categories"] = {}
        if stem not in active_cp["in_progress_categories"]:
            active_cp["in_progress_categories"][stem] = {}
        active_cp["in_progress_categories"][stem][cat] = cat_data
        active_cp["total_cooldown_wait_s"] = initial_cooldown_wait_s + groq_rate_limiter.total_wait_time
        save_checkpoint(active_cp, ACTIVE_CHECKPOINT_FILE)

    per_case_results: list[dict[str, Any]] = []

    try:
        if mode == "live" and max_concurrency > 1:
            with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
                futures = [
                    executor.submit(evaluate_case, stem, case_p, exp_p, client)
                    for stem, case_p, exp_p in fixtures
                ]
                for fut in futures:
                    per_case_results.append(fut.result())
        else:
            # Sequential execution
            for idx, (stem, case_p, exp_p) in enumerate(fixtures):
                if use_checkpoint and stem in completed_fixtures:
                    print(f"  [CHECKPOINT REUSED] Fixture {stem} already completed ({len(per_case_results) + 1}/{len(fixtures)}).")
                    per_case_results.append(completed_fixtures[stem])
                    continue

                print(f"  [EVALUATING] Fixture {stem} ({len(per_case_results) + 1}/{len(fixtures)})...")
                stem_in_prog = in_progress_categories.get(stem) if use_checkpoint else None
                res = evaluate_case(
                    fixture_stem=stem,
                    case_path=case_p,
                    expected_path=exp_p,
                    client=client,
                    in_progress_categories=stem_in_prog,
                    on_category_complete=on_category_complete if use_checkpoint else None,
                )
                per_case_results.append(res)

                if use_checkpoint:
                    completed_fixtures[stem] = res
                    active_cp.get("in_progress_categories", {}).pop(stem, None)
                    active_cp["completed_fixtures"] = completed_fixtures
                    active_cp["total_cooldown_wait_s"] = initial_cooldown_wait_s + groq_rate_limiter.total_wait_time
                    save_checkpoint(active_cp, ACTIVE_CHECKPOINT_FILE)
                    print(f"  [CHECKPOINT SAVED] Fixture {stem} completed and saved ({len(completed_fixtures)}/{len(fixtures)}).")
    finally:
        if live_client is not None:
            live_client.close()

    # Sort results by natural fixture name order
    per_case_results.sort(key=lambda r: natural_sort_key(r["fixture_stem"]))

    # Aggregate metrics
    tot_tp_a = sum(r["tier_a"]["tp"] for r in per_case_results)
    tot_fn_a = sum(r["tier_a"]["fn"] for r in per_case_results)
    tot_fp_a = sum(r["tier_a"]["fp"] for r in per_case_results)

    tot_tp_b = sum(r["tier_b"]["tp"] for r in per_case_results)
    tot_fn_b = sum(r["tier_b"]["fn"] for r in per_case_results)
    tot_fp_b = sum(r["tier_b"]["fp"] for r in per_case_results)
    tot_bonus_b = sum(r["tier_b"]["bonus_hits"] for r in per_case_results)
    tot_validated_b = sum(r["tier_b"]["validated_count"] for r in per_case_results)

    clean_fixtures = [r for r in per_case_results if r["clean"]]
    clean_cases_count = len(clean_fixtures)
    clean_cases_fp = sum((r["tier_a"]["fp"] + r["tier_b"]["fp"]) for r in clean_fixtures)

    tot_received = sum(r["rejections"]["received"] for r in per_case_results)
    tot_rejected = sum(r["rejections"]["rejected"] for r in per_case_results)
    agg_drop_reasons: dict[str, int] = {
        "schema_fail": 0,
        "type_mismatch": 0,
        "unresolved_ref": 0,
        "dismissal_guard": 0,
        "hallucination_suspected": 0,
        "deduped_by_tier_a": 0,
    }
    for r in per_case_results:
        for k, v in r["rejections"]["drop_reasons"].items():
            agg_drop_reasons[k] += v

    tier_a_recall = (tot_tp_a / (tot_tp_a + tot_fn_a)) if (tot_tp_a + tot_fn_a) > 0 else None
    tier_a_precision = (tot_tp_a / (tot_tp_a + tot_fp_a)) if (tot_tp_a + tot_fp_a) > 0 else None

    tier_b_recall = (tot_tp_b / (tot_tp_b + tot_fn_b)) if (tot_tp_b + tot_fn_b) > 0 else None
    tier_b_precision = ((tot_tp_b + tot_bonus_b) / tot_validated_b) if tot_validated_b > 0 else None

    hallucination_rate = (tot_rejected / tot_received) if tot_received > 0 else 0.0

    # Latency evaluation
    if mode == "live":
        all_case_latencies = [
            r["latency_ms"] for r in per_case_results
            if r.get("latency_ms") is not None and r["latency_ms"] > 0.0
        ]
        median_latency = statistics.median(all_case_latencies) if all_case_latencies else None
        if median_latency is not None:
            latency_display = f"{median_latency:.1f} ms"
            latency_status = "PASS" if median_latency < ACCEPTANCE_TARGETS["median_latency_ms"]["target"] else "FAIL"
        else:
            latency_display = "N/A"
            latency_status = "FAIL"
    elif mode == "stub":
        all_case_latencies = []
        median_latency = None
        latency_display = "N/A (stub replay)"
        latency_status = "N/A"
    else:  # dry_run
        all_case_latencies = []
        median_latency = None
        latency_display = "N/A (dry-run)"
        latency_status = "N/A"

    # Target compliance evaluation
    target_results: dict[str, Any] = {}

    def eval_metric(metric_name: str, val: float | None, target_spec: dict[str, Any]) -> str:
        if not target_spec.get("required", True):
            return "INFO"
        if val is None:
            return "N/A"
        op = target_spec["op"]
        tgt = target_spec["target"]
        if op == "==":
            return "PASS" if round(val, 4) == round(tgt, 4) else "FAIL"
        if op == ">=":
            return "PASS" if round(val, 4) >= round(tgt, 4) else "FAIL"
        if op == "<":
            return "PASS" if round(val, 4) < round(tgt, 4) else "FAIL"
        return "N/A"

    target_results["tier_a_recall"] = {
        "value": tier_a_recall,
        "target": ACCEPTANCE_TARGETS["tier_a_recall"]["display"],
        "status": eval_metric("tier_a_recall", tier_a_recall, ACCEPTANCE_TARGETS["tier_a_recall"]),
    }
    target_results["tier_a_precision"] = {
        "value": tier_a_precision,
        "target": ACCEPTANCE_TARGETS["tier_a_precision"]["display"],
        "status": "INFO",
    }
    target_results["tier_b_recall"] = {
        "value": tier_b_recall,
        "target": ACCEPTANCE_TARGETS["tier_b_recall"]["display"],
        "status": eval_metric("tier_b_recall", tier_b_recall, ACCEPTANCE_TARGETS["tier_b_recall"]),
    }
    target_results["tier_b_precision"] = {
        "value": tier_b_precision,
        "target": ACCEPTANCE_TARGETS["tier_b_precision"]["display"],
        "status": eval_metric("tier_b_precision", tier_b_precision, ACCEPTANCE_TARGETS["tier_b_precision"]),
    }
    target_results["hallucination_rate"] = {
        "value": hallucination_rate,
        "numerator": tot_rejected,
        "denominator": tot_received,
        "target": ACCEPTANCE_TARGETS["hallucination_rate"]["display"],
        "status": eval_metric("hallucination_rate", hallucination_rate, ACCEPTANCE_TARGETS["hallucination_rate"]),
        "policy": "Reviewed individually",
    }
    target_results["clean_cases_fp"] = {
        "value": clean_cases_fp,
        "clean_cases_count": clean_cases_count,
        "target": ACCEPTANCE_TARGETS["clean_cases_fp"]["display"],
        "status": eval_metric("clean_cases_fp", float(clean_cases_fp), ACCEPTANCE_TARGETS["clean_cases_fp"]),
    }
    target_results["median_latency_ms"] = {
        "value": median_latency,
        "display_value": latency_display,
        "target": ACCEPTANCE_TARGETS["median_latency_ms"]["display"],
        "status": latency_status,
        "policy": "Informational (retired as pass/fail criterion)",
    }

    # Aggregate status evaluation: no false PASS when a required analytical metric is N/A or FAIL.
    if mode == "live":
        # Analytical acceptance criteria (Prompt 12.2: latency 6000ms threshold retired, hallucination reviewed individually)
        required_targets = [
            "tier_a_recall",
            "tier_b_recall",
            "tier_b_precision",
            "clean_cases_fp",
        ]
    elif mode == "stub":
        required_targets = [
            "tier_a_recall",
            "tier_b_recall",
            "tier_b_precision",
            "hallucination_rate",
            "clean_cases_fp",
        ]
    else:  # dry_run
        required_targets = [
            "tier_a_recall",
            "tier_b_recall",
            "tier_b_precision",
            "hallucination_rate",
            "clean_cases_fp",
        ]

    passed_overall = all(
        target_results[k]["status"] == "PASS" for k in required_targets
    )

    total_benchmark_duration_s = time.time() - benchmark_start_time
    total_cooldown_wait_s = initial_cooldown_wait_s + (groq_rate_limiter.total_wait_time if live_client else 0.0)

    # Detailed latency metrics
    all_provider_latencies = [
        lat for r in per_case_results for lat in r.get("diagnostic_provider_latencies_ms", [])
        if lat is not None and lat > 0.0
    ]
    median_prov_lat = statistics.median(all_provider_latencies) if all_provider_latencies else None

    latency_details = {
        "provider_request_latency": {
            "count": len(all_provider_latencies),
            "median_ms": round(median_prov_lat, 2) if median_prov_lat is not None else None,
            "min_ms": round(min(all_provider_latencies), 2) if all_provider_latencies else None,
            "max_ms": round(max(all_provider_latencies), 2) if all_provider_latencies else None,
            "values": all_provider_latencies,
        },
        "complete_case_latency": {
            "count": len(all_case_latencies),
            "median_ms": round(median_latency, 2) if median_latency is not None else None,
            "min_ms": round(min(all_case_latencies), 2) if all_case_latencies else None,
            "max_ms": round(max(all_case_latencies), 2) if all_case_latencies else None,
            "values": all_case_latencies,
        },
        "total_cooldown_wait_seconds": round(total_cooldown_wait_s, 2),
        "total_benchmark_duration_seconds": round(total_benchmark_duration_s, 2),
    }

    # Finalize checkpoint when all fixtures complete
    if use_checkpoint and len(completed_fixtures) == len(fixtures):
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        archive_path = CHECKPOINTS_DIR / f"eval_checkpoint_{ts}.json"
        save_checkpoint(active_cp, archive_path)
        if ACTIVE_CHECKPOINT_FILE.exists():
            ACTIVE_CHECKPOINT_FILE.unlink()
        print(f"[CHECKPOINT] Finalized: archived to {archive_path.name} and cleaned active checkpoint.")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "max_concurrency": max_concurrency,
        "clean_cases_count": clean_cases_count,
        "total_fixtures_count": len(per_case_results),
        "fixtures": [r["fixture_stem"] for r in per_case_results],
        "per_case": per_case_results,
        "tier_a": {
            "tp": tot_tp_a,
            "fn": tot_fn_a,
            "fp": tot_fp_a,
            "recall": tier_a_recall,
            "precision": tier_a_precision,
        },
        "tier_b": {
            "tp": tot_tp_b,
            "fn": tot_fn_b,
            "fp": tot_fp_b,
            "bonus_hits": tot_bonus_b,
            "recall": tier_b_recall,
            "precision": tier_b_precision,
        },
        "rejections": {
            "received": tot_received,
            "rejected": tot_rejected,
            "rate": hallucination_rate,
            "drop_reasons": agg_drop_reasons,
        },
        "clean_cases_fp": clean_cases_fp,
        "latency_ms": {
            "median": median_latency,
            "display": latency_display,
            "values": all_case_latencies,
        },
        "latency_details": latency_details,
        "tokens": {
            "prompt_tokens": sum(r.get("tokens", {}).get("prompt_tokens", 0) for r in per_case_results),
            "completion_tokens": sum(r.get("tokens", {}).get("completion_tokens", 0) for r in per_case_results),
            "total_tokens": sum(r.get("tokens", {}).get("total_tokens", 0) for r in per_case_results),
            "total_requests": len(all_provider_latencies),
        },
        "checkpoint_info": {
            "resumption_count": resumption_count,
            "completed_sessions": resumption_count + 1,
        },
        "targets": target_results,
        "passed": passed_overall,
        "rate_limited_count": client.rate_limited_count,
        "errors": [err for r in per_case_results for err in r.get("errors", [])],
    }


# --- Report Formatting & Writing ---

def format_per_case_table(per_case_results: list[dict[str, Any]]) -> str:
    """Format Markdown per-case performance table."""
    lines = [
        "| Case | Clean? | A-recall | A-fp | B-recall | B-fp | Rejected/received |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in per_case_results:
        c_name = r["fixture_stem"]
        clean_str = str(r["clean"])
        a_rec = f"{r['tier_a']['recall']:.2f}" if r["tier_a"]["recall"] is not None else "N/A"
        a_fp = str(r["tier_a"]["fp"])
        b_rec = f"{r['tier_b']['recall']:.2f}" if r["tier_b"]["recall"] is not None else "N/A"
        b_fp = str(r["tier_b"]["fp"])
        rej_rec = f"{r['rejections']['rejected']}/{r['rejections']['received']}"
        lines.append(f"| {c_name} | {clean_str} | {a_rec} | {a_fp} | {b_rec} | {b_fp} | {rej_rec} |")
    return "\n".join(lines)


def format_aggregate_table(targets: dict[str, Any]) -> str:
    """Format Markdown aggregate acceptance metrics table."""
    lines = [
        "| Metric | Value | Target | Status |",
        "|---|---:|---:|---|",
    ]

    metric_rows = [
        ("Tier A recall", targets["tier_a_recall"]),
        ("Tier A precision", targets["tier_a_precision"]),
        ("Tier B recall", targets["tier_b_recall"]),
        ("Tier B precision", targets["tier_b_precision"]),
        ("Hallucination rate", targets["hallucination_rate"]),
        ("False positives on clean cases", targets["clean_cases_fp"]),
        ("Median latency", targets["median_latency_ms"]),
    ]

    for label, spec in metric_rows:
        val = spec["value"]
        if label == "Hallucination rate":
            num = spec.get("numerator", 0)
            den = spec.get("denominator", 0)
            val_str = f"{val:.2f} ({num}/{den})"
        elif label == "Median latency":
            val_str = spec.get("display_value") or (f"{val:.1f} ms" if val is not None else "N/A")
        elif isinstance(val, float):
            val_str = f"{val:.2f}"
        elif val is None:
            val_str = "N/A"
        else:
            val_str = str(val)

        target_str = spec["target"]
        if label == "Median latency" and spec.get("policy"):
            target_str = spec["policy"]
        elif label == "Hallucination rate" and spec.get("policy"):
            target_str = spec["policy"]

        status_str = spec["status"]
        lines.append(f"| {label} | {val_str} | {target_str} | {status_str} |")

    return "\n".join(lines)


def write_reports(eval_data: dict[str, Any], reports_dir: Path) -> tuple[Path, Path]:
    """Persist JSON and Markdown evaluation reports."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    json_path = reports_dir / f"eval_{ts}.json"
    md_path = reports_dir / f"eval_{ts}.md"

    # Write JSON report
    json_path.write_text(json.dumps(eval_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build Markdown report
    per_case_md = format_per_case_table(eval_data["per_case"])
    agg_md = format_aggregate_table(eval_data["targets"])
    status_overall = "PASS" if eval_data["passed"] else "FAIL"

    rejections = eval_data["rejections"]
    drop_reasons = rejections["drop_reasons"]
    drop_breakdown = ", ".join(f"{k}: {v}" for k, v in drop_reasons.items())

    clean_count = eval_data.get("clean_cases_count", 0)
    total_count = len(eval_data.get("fixtures", []))

    lat_info = eval_data.get("latency_details", {})
    prov_lat = lat_info.get("provider_request_latency", {})
    case_lat = lat_info.get("complete_case_latency", {})
    cooldown_s = lat_info.get("total_cooldown_wait_seconds", 0.0)
    duration_s = lat_info.get("total_benchmark_duration_seconds", 0.0)

    token_info = eval_data.get("tokens", {})
    cp_info = eval_data.get("checkpoint_info", {})

    md_content = f"""# Evaluation Report — {eval_data['timestamp']}

- **Mode:** `{eval_data['mode']}`
- **Concurrency:** `{eval_data['max_concurrency']}`
- **Fixtures Evaluated:** {total_count} (Clean fixtures: {clean_count})
- **Analytical Acceptance Status:** **{status_overall}**

## Per-Case Results

{per_case_md}

## Aggregate Acceptance Metrics

{agg_md}

### Validation Rejections & Drop Breakdown
- **Total Suggestions Received:** {rejections['received']}
- **Total Validator Dropped:** {rejections['rejected']}
- **Rejection Breakdown:** {drop_breakdown}

### Operational & Latency Analysis
- **Median Complete-Case Latency:** {case_lat.get('median_ms', 'N/A')} ms (Min: {case_lat.get('min_ms', 'N/A')} ms, Max: {case_lat.get('max_ms', 'N/A')} ms)
- **Median Provider Request Latency:** {prov_lat.get('median_ms', 'N/A')} ms (Requests: {prov_lat.get('count', 0)})
- **Total Cooldown Wait Time:** {cooldown_s:.2f} s
- **Total Benchmark Duration:** {duration_s:.2f} s
- **Total Token Consumption:** {token_info.get('total_tokens', 0)} (Prompt: {token_info.get('prompt_tokens', 0)}, Completion: {token_info.get('completion_tokens', 0)})
- **Checkpoint Resumptions:** {cp_info.get('resumption_count', 0)} (Completed over {cp_info.get('completed_sessions', 1)} session(s))

### Operational Policy & Notes
- **Latency Acceptance Retirement:** Median complete-case latency (<6000 ms) is retired as a pass/fail acceptance criterion per Prompt 12.2 to prioritize investigator-facing analytical correctness under provider rate limits.
- **Provider Rate Limiting:** 20-second transport cooldown enforced between consecutive Groq HTTP requests to protect 8,000 TPM limit.

*Audit records for individual cases are preserved in `runs/`.*
"""
    md_path.write_text(md_content, encoding="utf-8")
    return json_path, md_path


# --- CLI Entry Point ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluation harness for crime-scene case analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run-llm",
        action="store_true",
        default=False,
        help="Execute offline evaluation with empty deterministic LLM stub",
    )
    mode_group.add_argument(
        "--stub-llm",
        type=str,
        default=None,
        help="Path to pre-recorded JSON responses file for replay evaluation",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Maximum concurrent in-flight requests (positive integer)",
    )
    parser.add_argument(
        "--cases-dir",
        type=str,
        default=str(CASES_DIR),
        help="Path to directory containing case fixtures",
    )
    parser.add_argument(
        "--reports-dir",
        type=str,
        default=str(REPORTS_DIR),
        help="Path to directory where evaluation reports will be saved",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        default=False,
        help="Discard any existing active checkpoint and restart benchmark from scratch",
    )
    return parser


def main(args_list: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(args_list)

    # 1. Validate max-concurrency
    if args.max_concurrency <= 0:
        print(f"Error: --max-concurrency must be a positive integer, got {args.max_concurrency}", file=sys.stderr)
        return 2

    # 2. Determine mode
    if args.dry_run_llm:
        mode = "dry_run"
    elif args.stub_llm:
        mode = "stub"
    else:
        mode = "live"

    cases_dir = Path(args.cases_dir)
    reports_dir = Path(args.reports_dir)
    stub_path = Path(args.stub_llm) if args.stub_llm else None

    # 3. Print mode notice
    if mode == "dry_run":
        print("NOTE: This run used --dry-run-llm. Real accuracy requires a configured LLM provider.\n")

    # 4. Execute evaluation
    try:
        eval_data = evaluate_all(
            cases_dir=cases_dir,
            mode=mode,
            stub_path=stub_path,
            max_concurrency=args.max_concurrency,
            reset_checkpoint=args.reset_checkpoint,
        )
    except FileNotFoundError as err:
        print(f"Configuration/Fixture Error: {err}", file=sys.stderr)
        return 2
    except KeyError as err:
        print(f"Stub Replay Error: {err}", file=sys.stderr)
        return 2
    except Exception as err:
        print(f"Execution Error: {err}", file=sys.stderr)
        return 2

    # 5. Output Markdown tables to console
    print(format_per_case_table(eval_data["per_case"]))
    print()
    print(format_aggregate_table(eval_data["targets"]))
    print()

    # 6. Check rate limiting
    if eval_data.get("rate_limited_count", 0) > 0:
        print(
            f"WARNING: {eval_data['rate_limited_count']} requests were rate-limited; "
            "results may be incomplete. Re-run with --max-concurrency 1.\n",
            file=sys.stderr,
        )

    # 7. Write reports
    json_path, md_path = write_reports(eval_data, reports_dir)
    print(f"Reports saved:\n  JSON: {json_path}\n  Markdown: {md_path}")

    # 8. Determine exit code
    if eval_data["passed"]:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
