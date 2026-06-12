# AGENT OPERATIONAL RUNBOOK: Viral Curation and CAPHEINE Execution

This document provides instructions for AI agents orchestrating or maintaining this pipeline repository.

---

## 1. System Context & Input parameters

### Data Retrieval & Curation (`download_data.py`)
- **Inputs**:
  - NCBI Reference Accession: default `NC_014373.1` (BDBV).
  - Pathoplexus Metadata Endpoint: default `https://lapis.pathoplexus.org/ebola-bdbv/sample/details`.
  - Quality Filters: Sequence length $\ge 18,000$ bases, completeness score $\ge 0.90$.
- **Outputs**:
  - `bdbv_ref_cds.fasta`: Reference coding sequences for targeted structural/non-structural genes (NP, VP35, VP40, GP, VP30, VP24, L).
  - `assemblies/`: Directory containing curated full-length genomes.
  - `foreground_list.txt`: A list of outbreak-associated isolates classified into the foreground partition.

### Galaxy Execution & Resume Cache (`run_galaxy_pipeline.py`)
- **Credentials**: `GALAXY_API_KEY` (must be loaded from the environment or input stream; do not persist).
- **History Caching**: Maintains `galaxy_cache.json` containing:
  - `history_id`: Cached ID of the active run history.
  - `ref_dataset_id`: Cached ID of the reference CDS dataset on Galaxy.
  - `uploaded_datasets`: Map of genome names to their uploaded Galaxy dataset IDs.
  - `collection_id`: Cached ID of the unaligned assemblies list collection.
  - `workflow_id`: Cached ID of the imported CAPHEINE workflow.
- **Fail-Safe & Resume**: If interrupted, the agent or cron runner can restart the script. The script automatically reads `galaxy_cache.json`, validates dataset states on the server, and skips redundant uploads or collection creations.

---

## 2. Common Failures & Agent Remediation

| Failure Mode | Root Cause | Automated Agent Action |
| :--- | :--- | :--- |
| **Pathoplexus download times out** | Remote server latency or rate limits | Implement exponential backoff retry loop on the HTTP request in `download_data.py`. |
| **Galaxy Dataset in "error" state** | Invalid FASTA format or upload failure | Clean the corresponding cached ID in `galaxy_cache.json` (under `uploaded_datasets` or `ref_dataset_id`) to force re-upload. |
| **Workflow invocation fails (Bad Request)** | Galaxy API schema updates or version differences in parameter formats | Monitor outputs from the 8-candidate parameter configuration loop in `run_galaxy_pipeline.py`. If all fail, inspect the JSON response body and query the `/api/workflows/<id>/inputs` schema endpoint. |

---

## 3. Payload Candidate Specifications
To handle differences in Galaxy versions, the runner tries 8 payload configurations for workflow invocation:
1. **Candidate 1**: UUID-based step selection with parameters passed in `inputs` as raw strings.
2. **Candidate 2**: Index-based step selection with parameters passed in `inputs` as raw strings.
3. **Candidate 3**: UUID-based step selection with parameters passed in `inputs` as `{"value": "<string>"}` dicts.
4. **Candidate 4**: Index-based step selection with parameters passed in `inputs` as `{"value": "<string>"}` dicts.
5. **Candidate 5**: Index-based step selection with parameters passed in `params`.
6. **Candidate 6**: UUID-based step selection with parameters passed in `params`.
7. **Candidate 7**: UUID-based step selection omitting the optional regular expression parameters.
8. **Candidate 8**: Index-based step selection omitting the optional regular expression parameters.

If a candidate succeeds, the agent must log the matching candidate number for subsequent executions.

---

## 4. Safety & Compliance Constraints

- **Credential Isolation**: Under no circumstances should the agent write the `GALAXY_API_KEY` to the disk (except inside volatile environment variables) or output it to logs.
- **Git Safety**: Ensure `.gitignore` is present and active before initializing Git commits.
