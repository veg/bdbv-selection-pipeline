# Multi-Virus Evolutionary Selection Analysis Pipeline

This repository automates the curation of viral isolates and the execution of molecular evolutionary selection analyses. It supports obtaining full-length viral genomes (such as *Bundibugyo ebolavirus*, H5N1, Mpox, etc.) from **Pathoplexus** or **NCBI GenBank**, curating the isolates, and executing the **CAPHEINE** selection pipeline on a public Galaxy server.

---

## Features

- **Interactive Configuration Wizard**: Automatically prompts the user at start to define the target virus, genes, data source, and length thresholds, saving parameters to `pipeline_config.json`.
- **Dual Data Sources**:
  - **Pathoplexus**: Direct sample metadata and FASTA queries via LAPIS.
  - **NCBI GenBank**: Dynamic search term expansion and efetch downloads.
- **Gene-level Coding Sequence Extraction**: Downloads the reference GenBank record and extracts the exact CDS of target genes.
- **Galaxy Orchestration**: Fully automated upload, history organization, collection creation, and execution of the Nextflow-backed CAPHEINE workflow.
- **Result Aggregation**: Programmatic download and parsing of HyPhy results to produce a comprehensive selection report.

---

## Overview

The pipeline consists of three core phases, corresponding to three self-documenting Python scripts:

1. ** Curation & Retrieval (`download_data.py`)**
   - Automatically initializes the run configuration by prompting you if `pipeline_config.json` is missing.
   - Downloads the reference genome from NCBI RefSeq and extracts the coding sequences (CDS) of the target viral genes.
   - Queries either Pathoplexus or NCBI GenBank for sequence isolates, filtering them by genome length.
   - Classifies genomes into a "foreground" cohort (outbreak isolates) and a "background" cohort (historical reference genomes) based on your custom query, saving their FASTA sequences to `assemblies/`.

2. ** Galaxy Orchestration (`run_galaxy_pipeline.py`)**
   - Connects to a Galaxy instance (e.g., [usegalaxy.org](https://usegalaxy.org)) via the BioBlend API.
   - Uploads the reference CDS and all curated assemblies into a dedicated Galaxy history.
   - Groups the unaligned assemblies into a dataset collection.
   - Imports and triggers the Nextflow-backed **CAPHEINE** workflow (`Combined HyPhy Core and Compare`) to run codon-aware alignments, tree reconstruction, and the full suite of HyPhy selection tests (FEL, MEME, BUSTED, RELAX, Contrast-FEL).
   - Features a self-correcting parameter loop to resolve configuration payloads programmatically.

3. ** Results Retrieval & Processing (`download_and_process_results.py`)**
   - Polls the Galaxy history and downloads completed JSON/CSV results from the CAPHEINE run.
   - Parses the HyPhy JSON models to count significant positive and purifying selection sites.
   - Generates a local Markdown report (`selection_report.md`) summarizing the selection dynamics of the outbreak.

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

### 2. Configure and Download the Data
Run the curation script:
```bash
python download_data.py
```
If running for the first time, it will launch the configuration wizard. You will be prompted to enter:
- **Virus Name**: e.g., `Bundibugyo ebolavirus`
- **NCBI Reference Accession**: e.g., `NC_014373.1`
- **Target Genes**: e.g., `NP,VP35,VP40,GP,VP30,VP24,L`
- **Data Source**: Pathoplexus or NCBI GenBank
- **Minimum Genome Length**: e.g., `18000`
- **Foreground classification year/substring**: e.g., `2026` (classifies genomes with collection dates containing "2026" as foreground)

This creates `pipeline_config.json`, downloads all genomes to the `assemblies/` directory, extracts reference CDS, and generates `foreground_list.txt`.

### 3. Run CAPHEINE on Galaxy
Trigger the selection analysis workflow on the Galaxy infrastructure:
```bash
python run_galaxy_pipeline.py
```
The script will prompt for your API key if the environment variable is not set. It creates a dataset collection, imports the workflow definition, and executes the 113-job selection analysis suite.

> [!TIP]
> **Performance Optimization:** Uploading individual FASTA files as separate history items to Galaxy is slow and inefficient. For future enhancements, concatenate all assemblies into a single multi-FASTA file, upload it as a single dataset, and split it later using Galaxy's built-in split tools.

### 4. Fetch Results and Generate Report
Once the Galaxy jobs are complete (state: `ok`), download the results and generate a selection report:
```bash
python download_and_process_results.py
```
This parses the HyPhy results and compiles them into a markdown report (`selection_report.md`) summarizing gene-wide and site-level selection details.

---

## Security Warning

> [!CAUTION]
> Your Galaxy API key acts as your password. Never hardcode it in scripts or check it into Git. The scripts are pre-configured to look for the `GALAXY_API_KEY` environment variable or prompt you securely at runtime via `getpass`. The `.gitignore` file is configured to exclude local run directories and cached keys.
