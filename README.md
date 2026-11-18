# Crime Scene LLM Analysis Harness

CLI + evaluation harness that proves an LLM can generate grounded, citation-backed suggestions on structured crime-scene case data with zero hallucinations reaching the investigator.

See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for full architecture and specifications.

## Evaluation Harness (`evaluate.py`)

The evaluation harness evaluates the entire pipeline across all case fixtures with matching `.expected.json` files in `cases/`. It measures Tier A rule detection, Tier B grounded suggestion generation, validator rejection rates, clean case false positives, and end-to-end latency against the acceptance targets defined in `PROJECT_BRIEF.md`.

### Usage

- **Dry-run mode (offline logic validation without API spend):**
  ```bash
  python evaluate.py --dry-run-llm
  ```
  > **Note:** Dry-run mode validates harness and pipeline mechanics, schema compatibility, fixture loading, and Tier A rule detection. It does not validate LLM accuracy (Tier B suggestions will not be generated in dry run).

- **Stub mode (replay recorded LLM responses):**
  ```bash
  python evaluate.py --stub-llm path/to/responses.json
  ```
  Loads pre-recorded JSON responses keyed by case ID and analysis type to benchmark validator and metric logic deterministically.

- **Live evaluation (full end-to-end evaluation with live LLM):**
  ```bash
  python evaluate.py
  ```

- **Concurrency control (rate-limit mitigation):**
  ```bash
  python evaluate.py --max-concurrency 1
  ```
  Limits concurrent case processing (default: 4). Use `--max-concurrency 1` when operating under strict provider rate limits.

