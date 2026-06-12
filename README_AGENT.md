# AGENT OPERATIONAL RUNBOOK: Viral Curation and CAPHEINE Execution

This document provides instructions for AI agents orchestrating or maintaining this pipeline repository.

---

## 1. Programmatic Configuration & Pre-population

To prevent interactive CLI prompting (non-interactive runs, cron executions, or automated CI/CD runs), the agent should pre-create the `pipeline_config.json` file in the root directory before running `download_data.py`.

### Configuration Schema (`pipeline_config.json`)
```json
{
  "virus_name": "Bundibugyo ebolavirus",
  "ref_accession": "NC_014373.1",
  "target_genes": ["NP", "VP35", "VP40", "GP", "VP30", "VP24", "L"],
  "data_source": "pathoplexus",
  "lapis_db": "ebola-bdbv",
  "ncbi_search_term": "Orthoebolavirus bundibugyoense[Organism] AND human[Host]",
  "min_genome_length": 18000,
  "min_completeness": 0.90,
  "foreground_query_type": "date",
  "foreground_query_value": "2026",
  "galaxy_history_name": "Bundibugyo CAPHEINE Selection Analysis 2026",
  "foreground_suffix": "_foreground"
}
```

### Key Parameter Definitions:
- **`data_source`**: Must be either `"pathoplexus"` or `"ncbi"`.
- **`lapis_db`**: Required if `data_source` is `"pathoplexus"`. Set to the target LAPIS database name.
- **`ncbi_search_term`**: Required if `data_source` is `"ncbi"`. String term passed directly to Entrez ESearch.
- **`foreground_query_value`**: Substring matched against sequence collection dates to separate foreground vs. background isolates.

---

## 2. File Context & Output Pipeline

- **`download_data.py`** outputs:
  - `ref_cds.fasta`: Reference coding sequences for targeted genes.
  - `assemblies/`: Curated full-length genomes.
  - `foreground_list.txt`: Suffixes of foreground genomes.
- **`run_galaxy_pipeline.py`** outputs:
  - `galaxy_cache.json`: Stores `history_id`, `ref_dataset_id`, `uploaded_datasets` map, `collection_id`, and `workflow_id` to allow safe, step-wise resumption of executions.
- **`download_and_process_results.py`** outputs:
  - `selection_report.md`: Markdown summary report of evolutionary tests.

---

## 3. Common Failures & Agent Remediation

| Failure Mode | Root Cause | Automated Agent Action |
| :--- | :--- | :--- |
| **Pathoplexus download times out** | Remote server latency or rate limits | Implement exponential backoff retry loop on the HTTP request in `download_data.py`. |
| **NCBI Efetch Rate Limit** | Too many concurrent Entrez requests | Chunk NCBI fetches (e.g. 50 IDs at a time) and introduce a 1-second delay between requests. |
| **Galaxy Dataset in "error" state** | Invalid FASTA format or upload failure | Clean the corresponding cached ID in `galaxy_cache.json` (under `uploaded_datasets` or `ref_dataset_id`) to force re-upload. |
| **Workflow invocation fails (Bad Request)** | Galaxy API schema updates or version differences in parameter formats | Monitor outputs from the 8-candidate parameter configuration loop in `run_galaxy_pipeline.py`. If all fail, inspect the JSON response body and query the `/api/workflows/<id>/inputs` schema endpoint. |

---

## 4. Safety & Compliance Constraints

- **Credential Isolation**: Under no circumstances should the agent write the `GALAXY_API_KEY` to the disk (except inside volatile environment variables) or output it to logs.
- **Git Safety**: Ensure `.gitignore` is present and active before initializing Git commits.
