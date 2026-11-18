"""CLI entry point for running crime scene case analysis.

Parses command-line options, executes the analysis pipeline, and renders
structured findings and validation statistics to the terminal using rich.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.analysis.pipeline import run_pipeline
from src.llm import LLMConfigurationError, LLMConfig, PERMITTED_TIER_B_TYPES


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="AI-Assisted Crime Scene Investigation & Evidence Analysis CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "case_path",
        type=str,
        help="Path to case context JSON file (e.g. cases/C0.json)",
    )
    parser.add_argument(
        "--tier-a-only",
        action="store_true",
        default=False,
        help="Execute only the deterministic Tier A rules engine (no LLM calls)",
    )
    parser.add_argument(
        "--type",
        dest="analysis_type",
        type=str,
        choices=sorted(list(PERMITTED_TIER_B_TYPES)),
        default=None,
        help="Execute only the specified Tier B contradiction analysis category",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        default=False,
        help="Force execution of all three approved Tier B categories, bypassing semantic gate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional destination path to write full pipeline JSON results",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        default=False,
        help="Disable writing persistent audit records to the runs/ directory",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Override LLM provider (openai, gemini, anthropic)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model identifier",
    )
    return parser


def render_results(result: dict[str, Any], console: Console) -> None:
    """Render structured pipeline findings to terminal via rich."""
    case_id = result.get("case_id", "UNKNOWN")
    run_id = result.get("run_id", "UNKNOWN")
    status = result.get("status", "unknown").upper()
    gate_status = result.get("gate_status", "unknown")
    selected_categories = result.get("selected_categories", [])

    # 1. Header Panel
    status_color = "green" if status == "SUCCESS" else ("yellow" if status == "PARTIAL_SUCCESS" else "red")
    header_content = (
        f"[bold]Case ID:[/bold] {case_id}    [bold]Run ID:[/bold] {run_id}\n"
        f"[bold]Pipeline Status:[/bold] [{status_color}]{status}[/{status_color}]    "
        f"[bold]Gate Status:[/bold] {gate_status}\n"
        f"[bold]Tier B Categories:[/bold] {', '.join(selected_categories) if selected_categories else 'None'}"
    )
    console.print(Panel(header_content, title="Crime Scene Investigation Analysis", border_style="cyan"))

    # 2. Tier A Findings Table
    tier_a_flags = result.get("tier_a_flags", [])
    tier_a_table = Table(title=f"Tier A Findings ({len(tier_a_flags)})", border_style="blue")
    tier_a_table.add_column("Rule", style="bold yellow", width=8)
    tier_a_table.add_column("Target Ref", style="cyan", width=18)
    tier_a_table.add_column("Flag Type", style="magenta", width=20)
    tier_a_table.add_column("Description", style="white")

    if tier_a_flags:
        for flag in tier_a_flags:
            refs = ", ".join(flag.get("evidence_refs", []))
            tier_a_table.add_row(
                flag.get("rule", ""),
                refs,
                flag.get("flag_type", ""),
                flag.get("description", ""),
            )
    else:
        tier_a_table.add_row("-", "-", "No flags", "All Tier A structural checks passed cleanly.")
    console.print(tier_a_table)

    # 3. Tier B Suggestions Table
    tier_b_suggestions = result.get("tier_b_suggestions", [])
    tier_b_table = Table(title=f"Tier B Validated Suggestions ({len(tier_b_suggestions)})", border_style="green")
    tier_b_table.add_column("Type", style="cyan", width=24)
    tier_b_table.add_column("Severity", style="bold", width=10)
    tier_b_table.add_column("Cited Refs", style="yellow", width=20)
    tier_b_table.add_column("Summary & Reasoning", style="white")
    tier_b_table.add_column("Suggested Action", style="green")

    if tier_b_suggestions:
        for sug in tier_b_suggestions:
            sev = sug.get("severity", "medium")
            sev_color = "red" if sev == "high" else ("yellow" if sev == "medium" else "blue")
            refs = ", ".join(sug.get("evidence_refs", []))
            text = f"[bold]{sug.get('summary', '')}[/bold]\n{sug.get('reasoning', '')}"
            tier_b_table.add_row(
                sug.get("type", ""),
                f"[{sev_color}]{sev}[/{sev_color}]",
                refs,
                text,
                sug.get("suggested_action", ""),
            )
    else:
        tier_b_table.add_row("-", "-", "-", "No semantic contradictions found.", "-")
    console.print(tier_b_table)

    # 4. Invocations & Validator Audit Summary
    stats = result.get("stats", {})
    drop_reasons = stats.get("drop_reasons", {})
    audit_summary = (
        f"[bold]Suggestions Received:[/bold] {stats.get('received', 0)}  |  "
        f"[bold]Validated:[/bold] {stats.get('validated', 0)}  |  "
        f"[bold]Dropped by Validator:[/bold] {stats.get('rejected', 0)}\n"
        f"[bold]Drop Breakdown:[/bold] "
        f"Schema: {drop_reasons.get('schema_fail', 0)}, "
        f"Type: {drop_reasons.get('type_mismatch', 0)}, "
        f"Unresolved Ref: {drop_reasons.get('unresolved_ref', 0)}, "
        f"Dismissal Guard: {drop_reasons.get('dismissal_guard', 0)}, "
        f"Hallucination: {drop_reasons.get('hallucination_suspected', 0)}\n"
        f"[bold]Performance:[/bold] "
        f"Pipeline Latency: {stats.get('pipeline_latency_ms', 0):.1f} ms  |  "
        f"LLM Latency: {stats.get('total_latency_ms', 0):.1f} ms  |  "
        f"Total Tokens: {stats.get('total_tokens', 0)}"
    )
    if result.get("audit_path"):
        audit_summary += f"\n[bold]Audit Log:[/bold] [dim]{result.get('audit_path')}[/dim]"
    console.print(Panel(audit_summary, title="Audit & Performance Metrics", border_style="dim"))


def main(args_list: list[str] | None = None) -> int:
    """Main CLI entry point.
    
    Exit Codes:
        0: Success (including partial success where Tier A or some categories succeeded)
        1: Input error (file missing or unparseable JSON)
        2: Configuration error (invalid/missing provider or API key)
        3: Total execution failure (all Tier B categories failed)
    """
    parser = build_parser()
    args = parser.parse_args(args_list)
    console = Console()

    # 1. Validate case context input file
    case_path = Path(args.case_path)
    if not case_path.is_file():
        console.print(f"[bold red]Error:[/bold red] Case file not found: {case_path}")
        return 1

    try:
        case_context = json.loads(case_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[bold red]Error parsing case JSON:[/bold red] {exc}")
        return 1

    # 2. Configure LLM client if Tier B is required
    config: LLMConfig | None = None
    if not args.tier_a_only:
        try:
            config = LLMConfig(
                provider=args.provider,
                model=args.model,
            )
        except LLMConfigurationError as err:
            console.print(f"[bold red]LLM Configuration Error:[/bold red] {err}")
            return 2

    tier_b_types: list[str] | None = None
    if args.analysis_type:
        tier_b_types = [args.analysis_type]

    # 3. Execute pipeline
    result = run_pipeline(
        case_context=case_context,
        config=config,
        tier_b_types=tier_b_types,
        all_types=args.all_types,
        tier_a_only=args.tier_a_only,
        write_audit=not args.no_audit,
    )

    # 4. Render output to console
    render_results(result, console)

    # 5. Write output JSON if requested
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(dict(result), indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[dim]Results written to: {out_path}[/dim]")

    # 6. Exit code mapping
    if result.status == "failure":
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
