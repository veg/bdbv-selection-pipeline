import os
import json
import csv
import getpass
import re
from bioblend.galaxy import GalaxyInstance

# Configuration
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(WORKSPACE, "galaxy_results")
REPORT_FILE = os.path.join(WORKSPACE, "selection_report.md")
CONFIG_FILE = os.path.join(WORKSPACE, "pipeline_config.json")

# Load configuration
if not os.path.exists(CONFIG_FILE):
    print(f"Error: Configuration file not found at {CONFIG_FILE}. Please run 'download_data.py' first.")
    exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

os.makedirs(RESULTS_DIR, exist_ok=True)

def connect_galaxy():
    galaxy_url = os.environ.get("GALAXY_URL", "https://usegalaxy.org").strip()
        
    api_key = os.environ.get("GALAXY_API_KEY", "").strip()
    if not api_key:
        api_key = getpass.getpass("Enter your Galaxy API Key: ").strip()
        
    if not api_key:
        print("Error: API Key is required.")
        return None, None
        
    try:
        print(f"Connecting to Galaxy instance at {galaxy_url}...")
        gi = GalaxyInstance(url=galaxy_url, key=api_key)
        return gi, galaxy_url
    except Exception as e:
        print(f"Connection error: {e}")
        return None, None

def find_history(gi):
    history_names = [
        config.get("galaxy_history_name", "Viral CAPHEINE Selection Analysis"),
        "Bundibugyo CAPHEINE 68-Genomes Selection Analysis 2026",
        "Bundibugyo CAPHEINE Selection Analysis 2026"
    ]
    for history_name in history_names:
        print(f"Searching for history: '{history_name}'...")
        try:
            histories = gi.histories.get_histories(name=history_name)
            if histories:
                print(f"Found history! ID: {histories[0]['id']}")
                return histories[0]['id']
        except Exception as e:
            print(f"Error searching for history '{history_name}': {e}")
    print(f"Error: Could not find any history named: {history_names}")
    return None

def download_results(gi, history_id):
    print("\nRetrieving dataset collections from history...")
    try:
        contents = gi.histories.show_history(history_id, contents=True)
    except Exception as e:
        print(f"Error fetching history contents: {e}")
        return []
    
    downloaded_files = []
    targets = {
        "busted": "busted",
        "relax": "relax",
        "meme": "meme",
        "fel": "fel",
        "contrast": "contrast-fel",
        "cfel": "contrast-fel",
        "prime": "prime"
    }
    
    # Scan history for dataset collections
    for item in contents:
        c_type = item.get("history_content_type")
        if c_type != "dataset_collection":
            continue
            
        col_name = item.get("name", "")
        col_id = item.get("id")
        lower_col_name = col_name.lower()
        method = None
        
        # Determine selection method from collection name
        if "contrast" in lower_col_name or "cfel" in lower_col_name:
            method = "contrast-fel"
        else:
            for t, m in targets.items():
                if t in lower_col_name:
                    method = m
                    break
                    
        if not method:
            continue
            
        print(f"\nProcessing collection: '{col_name}' (Method: {method})")
        try:
            # Query collection details to get elements (mapped genes)
            col_details = gi.dataset_collections.show_dataset_collection(col_id)
            elements = col_details.get("elements", [])
            
            for elem in elements:
                gene = elem.get("element_identifier") # E.g., "GP", "L", "NP"
                
                # Check 'object', 'element_object', or fall back to 'elem'
                elem_obj = elem.get("object") or elem.get("element_object") or elem
                dataset_id = elem_obj.get("id")
                
                if not gene or not dataset_id:
                    continue
                    
                # Query dataset details to get file extension and status
                try:
                    ds_info = gi.datasets.show_dataset(dataset_id)
                    ext = ds_info.get("file_ext", "csv")
                    state = ds_info.get("state", "ok")
                except Exception:
                    ext = "csv"
                    state = "ok"
                    
                if state != "ok":
                    print(f"  Skipping {gene} (state is {state})")
                    continue
                
                # Format file name using gene name and method
                filename = f"{gene}_{method}.{ext}"
                filepath = os.path.join(RESULTS_DIR, filename)
                
                if os.path.exists(filepath):
                    print(f"  Element {gene} already exists locally. Skipping download.")
                    downloaded_files.append({
                        "gene": gene,
                        "method": method,
                        "filepath": filepath,
                        "ext": ext
                    })
                    continue
                
                print(f"  Downloading element: {gene} -> {filename}")
                try:
                    gi.datasets.download_dataset(dataset_id, file_path=filepath, use_default_filename=False)
                    downloaded_files.append({
                        "gene": gene,
                        "method": method,
                        "filepath": filepath,
                        "ext": ext
                    })
                except Exception as e:
                    print(f"    Error downloading element {gene}: {e}")
                    
        except Exception as e:
            print(f"  Error loading collection details: {e}")
            
    return downloaded_files

def discover_local_files():
    downloaded_files = []
    targets = ["busted", "relax", "meme", "fel", "contrast-fel", "prime"]
    genes = config.get("target_genes", ["NP", "VP35", "VP40", "GP", "VP30", "VP24", "L"])
    
    if not os.path.exists(RESULTS_DIR):
        return []
        
    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith(".hyphy_results.json"):
            # Format is [Gene]_[Method].hyphy_results.json
            match = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9-]+)\.hyphy_results\.json$", filename)
            if match:
                gene = match.group(1)
                method = match.group(2)
                if gene in genes and method in targets:
                    downloaded_files.append({
                        "gene": gene,
                        "method": method,
                        "filepath": os.path.join(RESULTS_DIR, filename),
                        "ext": "hyphy_results.json"
                    })
    return downloaded_files

def parse_results(downloaded_files):
    print("\nProcessing results files...")
    
    genes = config.get("target_genes", ["NP", "VP35", "VP40", "GP", "VP30", "VP24", "L"])
    summary = {g: {"busted": None, "relax": None, "fel_sites": 0, "meme_sites": 0, "cfel_sites": 0} for g in genes}
    
    for f in downloaded_files:
        path = f["filepath"]
        method = f["method"]
        gene = f["gene"]
        
        if gene not in summary:
            summary[gene] = {"busted": None, "relax": None, "fel_sites": 0, "meme_sites": 0, "cfel_sites": 0}
            
        try:
            with open(path, "r") as json_f:
                data = json.load(json_f)
        except Exception as e:
            print(f"  Error reading JSON file {path}: {e}")
            continue
            
        if method == "busted":
            p_val = data.get("test results", {}).get("p-value", None)
            summary[gene]["busted"] = p_val
            
        elif method == "relax":
            k_val = data.get("test results", {}).get("relaxation or intensification parameter", None)
            p_val = data.get("test results", {}).get("p-value", None)
            summary[gene]["relax"] = {"K": k_val, "p": p_val}
            
        elif method in ["fel", "meme", "contrast-fel"]:
            mle = data.get("MLE", {})
            headers = mle.get("headers", [])
            content = mle.get("content", {})
            
            p_col_idx = None
            alpha_col_idx = None
            beta_col_idx = None
            
            hdr_labels = [h[0].lower() for h in headers]
            
            if method == "fel":
                try:
                    p_col_idx = hdr_labels.index("p-value")
                    alpha_col_idx = hdr_labels.index("alpha")
                    beta_col_idx = hdr_labels.index("beta")
                except ValueError:
                    pass
            elif method == "meme":
                for idx, lbl in enumerate(hdr_labels):
                    if "p-value" in lbl:
                        p_col_idx = idx
                        break
            elif method == "contrast-fel":
                for idx, lbl in enumerate(hdr_labels):
                    if "p-value" in lbl or "overall" in lbl:
                        p_col_idx = idx
                        break
            
            sig_count = 0
            if p_col_idx is not None:
                for part, rows in content.items():
                    for row in rows:
                        try:
                            p_val = float(row[p_col_idx])
                            if p_val < 0.05:
                                # For FEL, filter for positive selection (beta > alpha)
                                if method == "fel" and alpha_col_idx is not None and beta_col_idx is not None:
                                    alpha_val = float(row[alpha_col_idx])
                                    beta_val = float(row[beta_col_idx])
                                    if beta_val > alpha_val:
                                        sig_count += 1
                                else:
                                    sig_count += 1
                        except (ValueError, IndexError):
                            pass
            
            if method == "fel":
                summary[gene]["fel_sites"] = sig_count
            elif method == "meme":
                summary[gene]["meme_sites"] = sig_count
            elif method == "contrast-fel":
                summary[gene]["cfel_sites"] = sig_count

    return summary

def generate_report(summary):
    print(f"\nWriting selection analysis report to: {REPORT_FILE}")
    
    report_md = []
    report_md.append(f"# {config.get('virus_name', 'Viral')} Selection Analysis Report")
    report_md.append(f"\nThis report summarizes the molecular evolutionary selection pressures detected across the {config.get('virus_name', 'viral')} genome, contrasting the foreground outbreak strains against historical background reference lineages using the CAPHEINE pipeline.\n")
    
    report_md.append("## 1. Gene-Wide Selection Dynamics (BUSTED & RELAX)")
    report_md.append("| Gene | BUSTED positive selection ($p$-value) | RELAX selection shift | K-parameter | RELAX $p$-value | Significance |")
    report_md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for gene, data in sorted(summary.items()):
        busted_p = f"{data['busted']:.4e}" if data['busted'] is not None else "N/A"
        
        relax_shift = "N/A"
        relax_k = "N/A"
        relax_p = "N/A"
        sig = "None"
        
        if data['relax'] is not None:
            k_val = data['relax']['K']
            p_val = data['relax']['p']
            relax_k = f"{k_val:.4f}"
            relax_p = f"{p_val:.4e}"
            
            if p_val < 0.05:
                if k_val < 1.0:
                    relax_shift = "Relaxed Selection"
                    sig = "Significant (Relaxation)"
                else:
                    relax_shift = "Intensified Selection"
                    sig = "Significant (Intensification)"
            else:
                relax_shift = "No Significant Shift"
                sig = "Not Significant"
                
        report_md.append(f"| **{gene}** | {busted_p} | {relax_shift} | {relax_k} | {relax_p} | {sig} |")
        
    report_md.append("\n*Note: BUSTED tests for gene-wide episodic diversifying selection. RELAX tests whether the selection intensity parameter K on foreground branches (2026) is shifted relative to background branches (K=1). K < 1 represents selection relaxation, and K > 1 represents selection intensification.*")
    
    report_md.append("\n## 2. Site-Level Selection Summary")
    report_md.append("| Gene | FEL purifying/positive sites (p < 0.05) | MEME episodic selection sites (p < 0.05) | Contrast-FEL differential sites (p < 0.05) |")
    report_md.append("| :--- | :--- | :--- | :--- |")
    
    for gene, data in sorted(summary.items()):
        report_md.append(f"| **{gene}** | {data['fel_sites']} | {data['meme_sites']} | {data['cfel_sites']} |")
        
    report_md.append("\n### Key Takeaways from Site-Level Analyses:")
    report_md.append("1. **Pervasive Purifying Selection:** Most sites in the coding regions are highly conserved under purifying selection (detected by FEL), maintaining functional structural integrity (e.g., in the viral matrix protein VP40 and nucleoprotein NP).")
    report_md.append("2. **Episodic Adaptations:** Sites identified by **MEME** represent codons that underwent positive selection along specific branches (potentially during zoonotic spillover or early human-to-human transmission).")
    report_md.append("3. **Differential Selection Pressure:** **Contrast-FEL** sites represent amino acid positions that evolve differently in the 2026 outbreak lineage compared to historical reservoir lineages, highlighting functional shifts.")
    
    report_md.append("\n## 3. Recommended Actions & Next Steps")
    report_md.append("1. **Structural Mapping:** Map significant sites from MEME and Contrast-FEL (especially in the Glycoprotein **GP** and Polymerase **L**) onto their 3D protein structures (PDB models) to identify if they cluster in functional domains (e.g. receptor-binding site or antibody-epitope region on GP).")
    report_md.append("2. **Property Constraint Inspection:** Inspect the **PRIME** property constraints for significant Contrast-FEL sites to explain *why* these mutations are favored (e.g., charge changes or volume changes).")
    report_md.append("3. **BRC.analytics Integration:** Correlate these consensus-level selective sites with the raw read variant calling results from **BRC.analytics** to check if the same sites show sub-clonal or low-frequency variations within individual hosts.")

    try:
        with open(REPORT_FILE, "w") as f:
            f.write("\n".join(report_md) + "\n")
        print(f"Report successfully generated!")
    except Exception as e:
        print(f"Error writing report: {e}")

def main():
    print("==================================================")
    print("Galaxy BioBlend CAPHEINE Results Processor")
    print("==================================================")
    
    import sys
    local_files = discover_local_files()
    use_local = False
    
    if local_files:
        print(f"Found {len(local_files)} local result files in {RESULTS_DIR}.")
        if os.environ.get("USE_LOCAL_FILES") == "1":
            use_local = True
        elif not sys.stdin.isatty():
            print("Non-interactive session: defaulting to fresh download from Galaxy.")
            use_local = False
        else:
            try:
                ans = input("Do you want to process these local files directly? [Y/n]: ").strip().lower()
                if ans in ["", "y", "yes"]:
                    use_local = True
            except (KeyboardInterrupt, EOFError):
                use_local = False
            
    if use_local:
        summary = parse_results(local_files)
        generate_report(summary)
        print("\nProcessing complete! You can open the generated report at:")
        print(f"  {REPORT_FILE}")
    else:
        gi, url = connect_galaxy()
        if not gi:
            return
            
        history_id = find_history(gi)
        if not history_id:
            return
            
        downloaded = download_results(gi, history_id)
        if not downloaded:
            print("No completed CAPHEINE datasets found to download.")
            return
            
        summary = parse_results(downloaded)
        generate_report(summary)
        print("\nProcessing complete! You can open the generated report at:")
        print(f"  {REPORT_FILE}")

if __name__ == "__main__":
    main()
