"""Menu-driven Investigator Interaction Workflow Prototype CLI.

Provides an interactive 9-option investigator interface wrapping the frozen
Module 1 analysis pipeline with complete result state presentation,
source record inspection, and review persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable

from src.workflow.adapter import (
    WorkflowAdapter,
    discover_cases,
    inspect_source_references,
    load_case_context,
)
from src.workflow.envelope import (
    EMPTY_SUGGESTIONS_MESSAGE,
    RESULT_STATE_EMPTY,
    RESULT_STATE_FAILURE,
    RESULT_STATE_FINDINGS,
    RESULT_STATE_PARTIAL,
    WorkflowRequest,
)
from src.workflow.store import WorkflowStore


class InvestigatorCLI:
    """Investigator CLI interface with injectable I/O for deterministic offline testing."""

    def __init__(
        self,
        adapter: WorkflowAdapter | None = None,
        store: WorkflowStore | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        cases_dir: Path | str | None = None,
    ) -> None:
        self.store = store or WorkflowStore()
        self.adapter = adapter or WorkflowAdapter(store=self.store)
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.cases_dir = Path(cases_dir) if cases_dir else None

        self.current_case_path: Path | None = None
        self.current_case_context: dict[str, Any] | None = None
        self.current_case_id: str | None = None
        self.latest_analysis_response: dict[str, Any] | None = None

    def run(self) -> None:
        """Run the main CLI interactive loop."""
        while True:
            self.output_fn("\n" + "=" * 55)
            self.output_fn("=== Crime Scene Evidence Analysis — Investigator CLI ===")
            self.output_fn("=" * 55)
            case_label = self.current_case_id or "None selected"
            self.output_fn(f"Current Case: {case_label}")
            self.output_fn("-" * 55)
            self.output_fn("1. Select Case")
            self.output_fn("2. Run Complete Analysis")
            self.output_fn("3. Run Spatial Inconsistency Analysis")
            self.output_fn("4. Run Timeline Contradiction Analysis")
            self.output_fn("5. Run Contextual Contradiction Analysis")
            self.output_fn("6. View Previous Analysis")
            self.output_fn("7. Review Findings")
            self.output_fn("8. View Case Analysis History")
            self.output_fn("9. Exit")
            self.output_fn("-" * 55)

            try:
                choice = self.input_fn("Select an option (1-9): ").strip()
            except (EOFError, KeyboardInterrupt):
                self.output_fn("\nExiting CLI session.")
                break

            if choice == "1":
                self._select_case()
            elif choice == "2":
                self._run_analysis(["spatial_inconsistency", "timeline_contradiction", "contextual_contradiction"])
            elif choice == "3":
                self._run_analysis(["spatial_inconsistency"])
            elif choice == "4":
                self._run_analysis(["timeline_contradiction"])
            elif choice == "5":
                self._run_analysis(["contextual_contradiction"])
            elif choice == "6":
                self._view_previous_analysis()
            elif choice == "7":
                self._review_findings()
            elif choice == "8":
                self._view_case_history()
            elif choice == "9":
                self.output_fn("Exiting Investigator CLI.")
                break
            else:
                self.output_fn("Invalid selection. Please choose an option from the menu (1-9).")

    # --- Option 1: Select Case ---

    def _select_case(self) -> None:
        cases = discover_cases(self.cases_dir)
        self.output_fn("\nAvailable Cases:")
        for idx, p in enumerate(cases, start=1):
            self.output_fn(f"  {idx}. {p.name}")
        self.output_fn("  C. Enter custom file path")
        self.output_fn("  B. Back to main menu")

        choice = self.input_fn("Select case number or option: ").strip()
        if choice.upper() == "B":
            return

        if choice.upper() == "C":
            custom_path_str = self.input_fn("Enter path to case JSON file: ").strip()
            target_path = Path(custom_path_str)
        elif choice.isdigit() and 1 <= int(choice) <= len(cases):
            target_path = cases[int(choice) - 1]
        elif Path(choice).is_file():
            target_path = Path(choice)
        else:
            self.output_fn(f"Invalid case selection: '{choice}'.")
            return

        try:
            ctx = load_case_context(target_path)
            self.current_case_path = target_path
            self.current_case_context = ctx
            self.current_case_id = str(ctx.get("case", {}).get("id") or target_path.stem)
            self.latest_analysis_response = None
            self.output_fn(f"Successfully loaded case '{self.current_case_id}' from {target_path}.")
        except Exception as exc:
            self.output_fn(f"Error loading case file: {exc}")

    # --- Options 2-5: Run Analysis ---

    def _run_analysis(self, analysis_types: list[str]) -> None:
        if self.current_case_context is None or self.current_case_id is None:
            self.output_fn("No case selected. Please select a case first using option 1.")
            return

        request = WorkflowRequest.create(
            case_id=self.current_case_id,
            case_context=self.current_case_context,
            analysis_types=analysis_types,
        )

        response = self.adapter.execute_request(request)
        self.latest_analysis_response = response
        self._present_results(response)

    # --- Present Results across all 4 states ---

    def _present_results(self, response: dict[str, Any]) -> None:
        data = response.get("data", {})
        result_state = data.get("result_state", "")

        self.output_fn("\n" + "-" * 55)
        self.output_fn(f"Analysis Status: {response.get('status')} | State: {result_state}")
        self.output_fn(f"Analysis ID: {data.get('analysis_id', 'N/A')}")
        self.output_fn("-" * 55)

        if result_state == RESULT_STATE_FINDINGS:
            self._present_findings_state(response)
        elif result_state == RESULT_STATE_EMPTY:
            self._present_empty_state(response)
        elif result_state == RESULT_STATE_PARTIAL:
            self._present_partial_state(response)
        elif result_state == RESULT_STATE_FAILURE:
            self._present_failure_state(response)
        else:
            self.output_fn(f"Unknown result state: {result_state}")

    def _present_findings_state(self, response: dict[str, Any]) -> None:
        data = response.get("data", {})
        suggestions = data.get("suggestions", [])
        tier_a_flags = data.get("tier_a_flags", [])

        self.output_fn(f"Findings Returned: {len(suggestions)} validated Tier B contradictions identified.")
        if tier_a_flags:
            self.output_fn(f"Tier A Deterministic Flags: {len(tier_a_flags)}")

        for idx, sug in enumerate(suggestions, start=1):
            sug_id = sug.get("suggestion_id", f"S{idx:03d}")
            sev = sug.get("severity", "unknown").upper()
            cat = sug.get("type", "unknown")
            summary = sug.get("summary", "")
            refs = ", ".join(sug.get("evidence_refs", []))

            self.output_fn(f"\n[Finding #{idx}] ID: {sug_id} | Category: {cat} | Severity: {sev}")
            self.output_fn(f"  Summary: {summary}")
            self.output_fn(f"  Evidence References: {refs}")
            self.output_fn(f"  Validation Status: Validated (passed 7-check audit gate)")

        warnings = response.get("warnings", [])
        if warnings:
            self.output_fn("\nWarnings:")
            for w in warnings:
                self.output_fn(f"  - {w}")

        self._findings_action_menu(response)

    def _present_empty_state(self, response: dict[str, Any]) -> None:
        self.output_fn(f"\n{EMPTY_SUGGESTIONS_MESSAGE}")

        warnings = response.get("warnings", [])
        if warnings:
            self.output_fn("\nAnalysis Notes:")
            for w in warnings:
                self.output_fn(f"  - {w}")

        self.output_fn("\nOptions:")
        self.output_fn("  1. Run another analysis category")
        self.output_fn("  2. View analysis details")
        self.output_fn("  3. Return to main menu")

        choice = self.input_fn("Select an option (1-3): ").strip()
        if choice == "1":
            self.output_fn("Return to main menu to select a different category (options 3, 4, or 5).")
        elif choice == "2":
            summary = response.get("data", {}).get("validation_summary", {})
            self.output_fn(f"Validation summary: {json.dumps(summary, indent=2)}")

    def _present_partial_state(self, response: dict[str, Any]) -> None:
        data = response.get("data", {})
        completed = data.get("completed_categories", [])
        ineligible = data.get("ineligible_categories", [])
        failed = data.get("failed_categories", [])
        retryable = data.get("retryable_categories", [])
        suggestions = data.get("suggestions", [])

        self.output_fn("\n=== Partial Completion Summary ===")
        self.output_fn(f"Completed Categories: {', '.join(completed) if completed else 'None'}")
        if ineligible:
            self.output_fn("Ineligible Categories (Gate Skipped):")
            for item in ineligible:
                self.output_fn(f"  - {item.get('category')}: {item.get('reason')}")
        if failed:
            self.output_fn("Failed Categories:")
            for item in failed:
                self.output_fn(f"  - {item.get('category')}: {item.get('error')}")

        if suggestions:
            self.output_fn(f"\nCompleted Findings ({len(suggestions)}):")
            for idx, sug in enumerate(suggestions, start=1):
                self.output_fn(f"  Finding #{idx} ({sug.get('suggestion_id')}): {sug.get('summary')}")

        self.output_fn("\nOptions:")
        if retryable:
            self.output_fn(f"  1. Retry failed eligible categories ({', '.join(retryable)})")
        self.output_fn("  2. Return to main menu")

        choice = self.input_fn("Select an option: ").strip()
        if choice == "1" and retryable:
            self.output_fn(f"Retrying eligible failed categories: {retryable}")
            self._run_analysis(retryable)

    def _present_failure_state(self, response: dict[str, Any]) -> None:
        errors = response.get("errors", [])
        self.output_fn("\n=== Technical Failure ===")
        self.output_fn("The analysis operation could not be completed.")
        for err in errors:
            self.output_fn(f"  Error: {err}")

        self.output_fn("\nOptions:")
        self.output_fn("  1. Retry analysis")
        self.output_fn("  2. View technical error details")
        self.output_fn("  3. Return to main menu")

        choice = self.input_fn("Select an option (1-3): ").strip()
        if choice == "1":
            self.output_fn("Returning to main menu to re-run analysis.")
        elif choice == "2":
            self.output_fn(f"Errors snapshot: {json.dumps(errors, indent=2)}")

    # --- Finding Action & Review Submenus ---

    def _findings_action_menu(self, response: dict[str, Any]) -> None:
        data = response.get("data", {})
        suggestions = data.get("suggestions", [])
        if not suggestions:
            return

        while True:
            self.output_fn("\nFindings Actions:")
            self.output_fn("  1. View source records for a finding")
            self.output_fn("  2. Review / update finding status")
            self.output_fn("  3. Return to main menu")

            try:
                choice = self.input_fn("Select action (1-3): ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if choice == "1":
                self._inspect_finding_source(suggestions)
            elif choice == "2":
                self._interactive_review(response)
            elif choice in ("3", "9") or choice.upper() == "B":
                break
            else:
                self.output_fn("Invalid selection.")

    def _inspect_finding_source(self, suggestions: list[dict[str, Any]]) -> None:
        if self.current_case_context is None:
            self.output_fn("No active case context.")
            return

        self.output_fn("\nSelect finding to inspect source records:")
        for idx, sug in enumerate(suggestions, start=1):
            self.output_fn(f"  {idx}. {sug.get('suggestion_id')}: {sug.get('summary')}")

        sel = self.input_fn("Enter finding number (or B to back): ").strip()
        if sel.upper() == "B" or not sel.isdigit():
            return
        idx = int(sel) - 1
        if not (0 <= idx < len(suggestions)):
            self.output_fn("Invalid finding number.")
            return

        target_sug = suggestions[idx]
        refs = target_sug.get("evidence_refs", [])
        self.output_fn(f"\nInspecting source records for {target_sug.get('suggestion_id')} (Refs: {', '.join(refs)}):")
        records = inspect_source_references(self.current_case_context, refs)
        for ref, rec in records.items():
            self.output_fn(f"\n--- Reference: {ref} ---")
            self.output_fn(json.dumps(rec, indent=2, ensure_ascii=False) if rec is not None else "Reference could not be resolved.")

    def _interactive_review(self, response: dict[str, Any]) -> None:
        data = response.get("data", {})
        analysis_id = data.get("analysis_id")
        suggestions = data.get("suggestions", [])
        if not analysis_id or not suggestions:
            self.output_fn("No active findings to review.")
            return

        self.output_fn("\nSelect finding to review:")
        for idx, sug in enumerate(suggestions, start=1):
            sug_id = sug.get("suggestion_id", f"S{idx:03d}")
            curr_status = self.store.get_latest_review_status(analysis_id, sug_id)
            self.output_fn(f"  {idx}. [{curr_status.upper()}] {sug_id}: {sug.get('summary')}")

        sel = self.input_fn("Enter finding number (or B to back): ").strip()
        if sel.upper() == "B" or not sel.isdigit():
            return
        idx = int(sel) - 1
        if not (0 <= idx < len(suggestions)):
            self.output_fn("Invalid finding number.")
            return

        target_sug = suggestions[idx]
        sug_id = target_sug.get("suggestion_id", f"S{idx:03d}")

        self.output_fn(f"\nReviewing Finding {sug_id}:")
        self.output_fn(f"  Category: {target_sug.get('type')}")
        self.output_fn(f"  Summary: {target_sug.get('summary')}")
        self.output_fn("  Decision Options:")
        self.output_fn("    1. Acknowledged (Note: Acknowledgement does not establish factual truth.)")
        self.output_fn("    2. Not Relevant (Mandatory explanation required)")
        self.output_fn("    3. Deferred (Postpone review)")
        self.output_fn("    B. Cancel")

        dec = self.input_fn("Select decision (1-3): ").strip()
        if dec == "1":
            comment = self.input_fn("Optional notes: ").strip()
            self.store.record_review(
                analysis_id=analysis_id,
                suggestion_id=sug_id,
                review_status="acknowledged",
                comment=comment,
            )
            self.output_fn(f"Finding marked as acknowledged. (Note: Acknowledgement does not establish factual truth.)")
        elif dec == "2":
            reason = self.input_fn("Enter mandatory reason for dismissal: ").strip()
            if not reason:
                self.output_fn("A non-empty reason is mandatory when marking a finding as not relevant.")
                return
            self.store.record_review(
                analysis_id=analysis_id,
                suggestion_id=sug_id,
                review_status="not_relevant",
                comment=reason,
            )
            self.output_fn("Finding marked as not relevant.")
        elif dec == "3":
            comment = self.input_fn("Optional deferral note: ").strip()
            self.store.record_review(
                analysis_id=analysis_id,
                suggestion_id=sug_id,
                review_status="deferred",
                comment=comment,
            )
            self.output_fn("Finding marked as deferred.")
        else:
            self.output_fn("Review cancelled.")

    # --- Option 6: View Previous Analysis ---

    def _view_previous_analysis(self) -> None:
        if self.current_case_id is None:
            self.output_fn("No case selected. Please select a case first using option 1.")
            return

        rec = self.store.get_latest_analysis(self.current_case_id)
        if not rec:
            self.output_fn(f"No previous analysis found for case '{self.current_case_id}'.")
            return

        self.output_fn(f"Displaying latest analysis snapshot recorded at {rec.get('created_at')}.")
        snapshot = rec.get("response_snapshot", {})
        self.latest_analysis_response = snapshot
        self._present_results(snapshot)

    # --- Option 7: Review Findings ---

    def _review_findings(self) -> None:
        if self.current_case_id is None:
            self.output_fn("No case selected. Please select a case first using option 1.")
            return

        active_response = self.latest_analysis_response
        if not active_response:
            latest_rec = self.store.get_latest_analysis(self.current_case_id)
            if latest_rec:
                active_response = latest_rec.get("response_snapshot")
                self.latest_analysis_response = active_response

        if not active_response:
            self.output_fn("No analysis results found to review. Please run an analysis first.")
            return

        suggestions = active_response.get("data", {}).get("suggestions", [])
        if not suggestions:
            self.output_fn("No findings in the current analysis.")
            return

        self._interactive_review(active_response)

    # --- Option 8: View Case Analysis History ---

    def _view_case_history(self) -> None:
        if self.current_case_id is None:
            self.output_fn("No case selected. Please select a case first using option 1.")
            return

        history = self.store.get_case_history(self.current_case_id)
        if not history:
            self.output_fn(f"No analysis history recorded for case '{self.current_case_id}'.")
            return

        self.output_fn(f"\nAnalysis History for Case '{self.current_case_id}' ({len(history)} runs):")
        self.output_fn(f"{'#':<3} {'Analysis ID':<30} {'Timestamp':<22} {'State':<20} {'Findings':<8}")
        self.output_fn("-" * 85)
        for idx, item in enumerate(history, start=1):
            snap = item.get("response_snapshot", {})
            data = snap.get("data", {})
            findings_count = len(data.get("suggestions", []))
            self.output_fn(
                f"{idx:<3} {item.get('analysis_id', 'N/A'):<30} "
                f"{item.get('created_at', 'N/A'):<22} "
                f"{data.get('result_state', 'N/A'):<20} "
                f"{findings_count:<8}"
            )


def main() -> None:
    """CLI executable entry point."""
    cli = InvestigatorCLI()
    cli.run()


if __name__ == "__main__":
    main()
