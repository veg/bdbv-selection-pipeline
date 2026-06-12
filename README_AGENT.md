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

---

## 5. Optimization & Performance Guidelines

- **Batch Uploading to Galaxy:** Do **NOT** upload individual FASTA files for assemblies as separate history items. This causes massive overhead (90+ upload jobs and UI clutter) and is highly inefficient. Instead, upload a single combined FASTA file containing all curated assemblies, and split it into a dataset collection on Galaxy using a split tool, or adjust the workflow to accept a combined FASTA.

---

## 6. Joint RELAX Analysis: Execution & Interpretation

To test for shifts in natural selection intensity during zoonotic emergence, agents should execute a multi-gene joint RELAX analysis.

### Step 1: Data Preparation & Labeling
1. **Exclusions**: Check the leaf topology of each gene tree. If a gene tree has only a single foreground isolate (e.g., `VP30` in the 2026 BDBV outbreak), **exclude it from multi-label runs**. A single foreground tip collapses the ancestral MRCA node and the terminal tip into a single branch, meaning there are no descendant branches to label `{2026}`, causing HyPhy to crash.
2. **Three-Label Annotation**: Annotate the Newick trees with three distinct labels:
   * `{TEST}` on the ancestral MRCA branch of the outbreak.
   * `{2026}` on all internal and terminal branches of the outbreak clade.
   * `{background}` on all other historical outbreak branches.
3. **Filelist**: Create a flat text file (`relax_filelist_no_vp30.txt`) listing the absolute paths to the in-frame codon alignments in the exact same order as the `--tree` arguments.

### Step 2: Running the Joint Analyses
Agents must run two separate configurations using the same 3-label trees to capture both levels of evolutionary change:

#### Run A: Ancestral MRCA Test
To test for selection shifts specifically during spillover (along the ancestral stem branch):
```bash
hyphy relax \
  --multiple-files Yes \
  --filelist /path/to/relax_filelist_no_vp30.txt \
  --rates 2 \
  --test TEST \
  --reference background \
  --models Minimal \
  --tree /path/to/NP_labeled.tree ...
```
*In this run, `{TEST}` is the Test set, `{background}` is the Reference, and the descendant `{2026}` branches are treated as the third (unclassified nuisance) group.*

#### Run B: Outbreak Clade Test
To test for selection shifts during ongoing human-to-human transmission (within the outbreak clade):
```bash
hyphy relax \
  --multiple-files Yes \
  --filelist /path/to/relax_filelist_no_vp30.txt \
  --rates 2 \
  --test 2026 \
  --reference background \
  --models Minimal \
  --tree /path/to/NP_labeled.tree ...
```
*In this run, `{2026}` is the Test set, `{background}` is the Reference, and the ancestral MRCA branch `{TEST}` is treated as the third (unclassified nuisance) group.*

### Step 3: Interpreting the Outputs
1. **LRT Significance ($p$-value)**:
   * If $p > 0.05$, there is **no statistically significant shift** in selection intensity. Both EBOV/BDBV runs show no shift ($p = 0.3014$ and $p = 0.5255$), validating a direct spillover model without altered selective pressures.
2. **Selection Intensity ($K$ parameter)**:
   * **$K \approx 1$**: Evolutionary dynamics are indistinguishable from baseline transmission.
   * **$K > 1$**: Intensified selection (both positive and purifying selection are stronger).
   * **$K < 1$**: Relaxed selection. If $K < 1$ significantly ($p \le 0.05$), this represents the evolutionary fingerprint of **laboratory passaging** (e.g. in cell culture or vaccine attenuation) where selective constraints are removed.
3. **Unbalanced Models**: If the background database has no positive selection ($\omega > 1$), an increase in $\omega$ in the test set will be evaluated as a relaxation of purifying selection rather than positive selection. Agents should note this as an "unbalanced model" in the final reports.
