# BDBV Evolutionary Selection Analysis Pipeline

This repository automates the curation of viral isolates and the execution of molecular evolutionary selection analyses. Specifically, it guides the process of obtaining full-length viral genomes (such as *Bundibugyo ebolavirus* - BDBV) from **Pathoplexus** and the **NCBI RefSeq** database, curating the isolates, and executing the **CAPHEINE** selection pipeline on a public Galaxy server.

---

## Overview

The pipeline consists of three core phases, corresponding to three self-documenting Python scripts:

1. ** Curation & Retrieval (`download_data.py`)**
   - Downloads the reference genome from NCBI RefSeq and extracts the coding sequences (CDS) of the target viral genes (NP, VP35, VP40, GP, VP30, VP24, L).
   - Queries the Pathoplexus API to search for all high-quality, full-length isolates (filtering for length $\ge$ 18k bp and completeness $\ge$ 90%).
   - Classifies genomes into a "foreground" cohort (e.g., May 2026 outbreak isolates) and a "background" cohort (historical reference genomes) based on collection date, downloading their FASTA sequences.

2. ** Galaxy Orchestration (`run_galaxy_pipeline.py`)**
   - Connects to a Galaxy instance (e.g., [usegalaxy.org](https://usegalaxy.org)) via the BioBlend API.
   - Uploads the reference CDS and all curated assemblies into a dedicated Galaxy history.
   - Groups the unaligned assemblies into a dataset collection.
   - Imports and triggers the Nextflow-backed **CAPHEINE** workflow (`Combined HyPhy Core and Compare`) to run codon-aware alignments, tree reconstruction, and the full suite of HyPhy selection tests (FEL, MEME, BUSTED, RELAX, Contrast-FEL).
   - Features a self-correcting parameter loop to resolve configuration payloads programmatically.

3. ** Results Retrieval & Processing (`download_process_results.py`)**
   - Polls the Galaxy history and downloads completed JSON/CSV results from the CAPHEINE run.
   - Parses the HyPhy JSON models to count significant positive and purifying selection sites.
   - Generates a local Markdown report (`ebov_selection_report.md`) summarizing the selection dynamics of the outbreak.

---

## Requirements

- Python 3.8+
- Active Galaxy account and API key (obtainable from Galaxy User -> Preferences -> Manage API Key)
- Packages: `biopython`, `bioblend`

Install dependencies:
```bash
pip install biopython bioblend
```

---

## Installation & Usage

### 1. Setup Your Environment
Set your Galaxy API key as an environment variable to avoid entering it manually. **Do not hardcode your API key in the scripts or commit it to Git!**

```bash
export GALAXY_API_KEY="your_actual_api_key"
export GALAXY_URL="https://usegalaxy.org"
```

### 2. Download and Curate the Data
Run the curation script to download the reference and sequence assemblies:
```bash
python download_data.py
```
This downloads all genomes to the `assemblies/` directory, extracts reference CDS, and generates `foreground_list.txt`.

### 3. Run CAPHEINE on Galaxy
Trigger the selection analysis workflow on the Galaxy infrastructure:
```bash
python run_galaxy_pipeline.py
```
The script will prompt for your API key if the environment variable is not set. It creates a dataset collection, imports the workflow definition, and executes the 113-job selection analysis suite.

### 4. Fetch Results and Generate Report
Once the Galaxy jobs are complete (state: `ok`), download the results and generate a selection report:
```bash
python download_and_process_results.py
```
This parses the HyPhy results and compiles them into a markdown report summarizing gene-wide and site-level selection details.

---

## Security Warning

> [!CAUTION]
> Your Galaxy API key acts as your password. Never hardcode it in scripts or check it into Git. The scripts are pre-configured to look for the `GALAXY_API_KEY` environment variable or prompt you securely at runtime via `getpass`. The `.gitignore` file is configured to exclude local run directories and cached keys.
