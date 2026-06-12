import os
import io
import urllib.request
import json
import re
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

# Configuration File Path
CONFIG_FILE = "pipeline_config.json"

def load_config_or_prompt():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read configuration file: {e}")
            
    print("==================================================")
    print("      Viral Pipeline Configuration Wizard         ")
    print("==================================================")
    print("No pipeline_config.json found. Let's configure your run.")
    
    config = {}
    config["virus_name"] = input("Virus Name (e.g., Bundibugyo ebolavirus): ").strip()
    config["ref_accession"] = input("NCBI Reference Genome Accession (e.g., NC_014373.1): ").strip()
    
    genes_raw = input("Target Genes to extract (comma-separated, e.g., NP,VP35,VP40,GP,VP30,VP24,L): ").strip()
    config["target_genes"] = [g.strip() for g in genes_raw.split(",") if g.strip()]
    
    source = input("Data Source for isolates [1: Pathoplexus, 2: NCBI GenBank]: ").strip()
    if source == "1":
        config["data_source"] = "pathoplexus"
        config["lapis_db"] = input("Pathoplexus LAPIS DB Name (e.g., ebola-bdbv, h5n1): ").strip()
    else:
        config["data_source"] = "ncbi"
        config["lapis_db"] = ""
        config["ncbi_search_term"] = input("NCBI search term for isolates (e.g., Orthoebolavirus bundibugyoense[Organism] AND human[Host]): ").strip()
        
    config["min_genome_length"] = int(input("Minimum genome length for curation (e.g., 18000): ") or 18000)
    config["min_completeness"] = float(input("Minimum completeness (Pathoplexus only, e.g., 0.90): ") or 0.90)
    
    config["foreground_query_type"] = "date"
    config["foreground_query_value"] = input("Foreground classification year/substring (e.g., 2026): ").strip()
    config["galaxy_history_name"] = input("Galaxy History Name: ").strip() or f"{config['virus_name']} Selection Analysis"
    config["foreground_suffix"] = "_foreground"
    
    # Save Configuration
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\nConfiguration saved to {CONFIG_FILE}!\n")
    return config

# Load Configuration
config = load_config_or_prompt()

# Paths
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
ASSEMBLIES_DIR = os.path.join(WORKSPACE, "assemblies")
os.makedirs(ASSEMBLIES_DIR, exist_ok=True)

REF_ACC = config["ref_accession"]
REF_CDS_FILE = os.path.join(WORKSPACE, "ref_cds.fasta")
FOREGROUND_LIST_FILE = os.path.join(WORKSPACE, "foreground_list.txt")

# 1. DOWNLOAD AND CONSTRUCT REFERENCE CDS FASTA
print(f"Step 1: Downloading Reference Genome {REF_ACC} from NCBI...")
ref_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id={REF_ACC}&retmode=text&rettype=gb"
req = urllib.request.Request(ref_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    ref_gb_text = resp.read().decode('utf-8')

ref_record = SeqIO.read(io.StringIO(ref_gb_text), 'genbank')
ref_cds_records = []

target_genes = config["target_genes"]
extracted_genes = set()

for feat in ref_record.features:
    if feat.type == 'CDS':
        gene = feat.qualifiers.get('gene', [''])[0]
        product = feat.qualifiers.get('product', [''])[0]
        
        # Special case for Orthoebolavirus GP gene to get the full-length spike glycoprotein
        if "ebola" in config["virus_name"].lower() and gene == "GP" and product and "spike glycoprotein" not in product.lower():
            continue
            
        if gene in target_genes and gene not in extracted_genes:
            extracted_genes.add(gene)
            cds_seq = feat.extract(ref_record.seq)
            
            # Clean gene name
            record_id = gene
            rec = SeqRecord(cds_seq, id=record_id, name="", description=product)
            ref_cds_records.append(rec)
            print(f"  Extracted gene: {gene} (Length: {len(cds_seq)} bp)")

# Write reference CDS FASTA
with open(REF_CDS_FILE, "w") as f:
    SeqIO.write(ref_cds_records, f, "fasta")
print(f"Reference CDS saved to {REF_CDS_FILE}\n")

# 2. QUERY SOURCE FOR METADATA AND DOWNLOAD
foreground_headers = []

if config["data_source"] == "pathoplexus" and config["lapis_db"]:
    print(f"Step 2: Querying Pathoplexus for {config['virus_name']} genomes...")
    lapis_url = f"https://lapis.pathoplexus.org/{config['lapis_db']}/sample/details"
    req = urllib.request.Request(lapis_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        metadata = json.loads(resp.read().decode())
    
    samples = metadata.get('data', [])
    print(f"Found {len(samples)} total records in Pathoplexus.")
    
    # Filter for quality and version
    latest_versions = {}
    for s in samples:
        acc = s.get('accession')
        version = s.get('version', 1)
        length = s.get('length', 0)
        comp = s.get('completeness', 0.0)
        
        if length < config["min_genome_length"] or comp < config["min_completeness"]:
            continue
            
        # Skip known duplicate sequence PP_006Y8S4 if BDBV
        if acc == 'PP_006Y8S4':
            continue
            
        if acc not in latest_versions or version > latest_versions[acc]['version']:
            latest_versions[acc] = s
            
    print(f"Curated {len(latest_versions)} unique high-quality genomes.")
    
    # Group and download
    for acc, s in sorted(latest_versions.items()):
        coll_date = s.get('sampleCollectionDate', '')
        country = s.get('geoLocCountry') or 'Unknown'
        country = country.replace(' ', '_').replace('(', '').replace(')', '')
        version = s.get('version', 1)
        
        # Check if foreground
        is_fg = config["foreground_query_value"] in coll_date if coll_date else False
        suffix = "foreground" if is_fg else "background"
        
        clean_name = f"{country}_{acc}_{version}_{coll_date or 'historical'}_{suffix}"
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)
        out_path = os.path.join(ASSEMBLIES_DIR, f"{clean_name}.fasta")
        
        if is_fg:
            foreground_headers.append(clean_name)
            
        if os.path.exists(out_path):
            print(f"  {clean_name}.fasta already exists. Skipping.")
            continue
            
        seq_url = f"https://pathoplexus.org/seq/{acc}.fa"
        print(f"  Downloading {acc}...")
        try:
            seq_req = urllib.request.Request(seq_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(seq_req) as seq_resp:
                seq_text = seq_resp.read().decode('utf-8')
            parsed = list(SeqIO.parse(io.StringIO(seq_text), 'fasta'))
            if parsed:
                parsed[0].id = clean_name
                parsed[0].name = ""
                parsed[0].description = ""
                with open(out_path, "w") as out_f:
                    SeqIO.write(parsed[0], out_f, "fasta")
                print(f"    Saved: {clean_name}.fasta")
        except Exception as e:
            print(f"    Error downloading {acc}: {e}")

else:
    # NCBI GenBank Source
    print(f"Step 2: Searching NCBI GenBank for {config['virus_name']} isolates...")
    search_term = config.get("ncbi_search_term") or f"{config['virus_name']}[Organism] AND human[Host]"
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nucleotide&term={urllib.parse.quote(search_term)}&retmode=json&retmax=100"
    
    req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        search_res = json.loads(resp.read().decode())
        
    ids = search_res.get("esearchresult", {}).get("idlist", [])
    print(f"Found {len(ids)} matching genome IDs in NCBI GenBank.")
    
    # Download details and filter
    if ids:
        ids_str = ",".join(ids)
        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nucleotide&id={ids_str}&retmode=json"
        
        req = urllib.request.Request(summary_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            summary_res = json.loads(resp.read().decode())
            
        results = summary_res.get("result", {})
        
        for uid in ids:
            if uid == "uid":
                continue
            item = results.get(uid, {})
            acc = item.get("accessionversion", uid)
            title = item.get("title", "")
            
            # Simple length check from summary if available
            length = int(item.get("slen") or 0)
            if length < config["min_genome_length"]:
                continue
                
            # Fetch full GenBank record to get collection date and country
            print(f"  Fetching metadata for {acc}...")
            details_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id={acc}&retmode=text&rettype=gb"
            try:
                d_req = urllib.request.Request(details_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(d_req) as d_resp:
                    gb_text = d_resp.read().decode('utf-8')
                rec = SeqIO.read(io.StringIO(gb_text), 'genbank')
                
                coll_date = ""
                country = "Unknown"
                for feat in rec.features:
                    if feat.type == "source":
                        coll_date = feat.qualifiers.get("collection_date", [""])[0]
                        country = feat.qualifiers.get("country", ["Unknown"])[0].split(":")[0]
                        break
                
                country = country.replace(' ', '_').replace('(', '').replace(')', '')
                is_fg = config["foreground_query_value"] in coll_date if coll_date else False
                suffix = "foreground" if is_fg else "background"
                
                clean_name = f"{country}_{acc}_1_{coll_date or 'historical'}_{suffix}"
                clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)
                out_path = os.path.join(ASSEMBLIES_DIR, f"{clean_name}.fasta")
                
                if is_fg:
                    foreground_headers.append(clean_name)
                    
                if os.path.exists(out_path):
                    print(f"    Already exists. Skipping.")
                    continue
                    
                # Save sequence
                rec.id = clean_name
                rec.name = ""
                rec.description = ""
                with open(out_path, "w") as out_f:
                    SeqIO.write(rec, out_f, "fasta")
                print(f"    Saved: {clean_name}.fasta")
                
            except Exception as e:
                print(f"    Error processing {acc}: {e}")

# Save foreground headers list
with open(FOREGROUND_LIST_FILE, "w") as f:
    f.write("\n".join(foreground_headers) + "\n")
print(f"\nForeground list saved to {FOREGROUND_LIST_FILE}")

print("\nData preparation complete!")
