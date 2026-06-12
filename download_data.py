import os
import io
import urllib.request
import json
import re
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

# Paths
WORKSPACE = "/Users/sergei/Dropbox/Work/EBOV"
ASSEMBLIES_DIR = os.path.join(WORKSPACE, "assemblies")
os.makedirs(ASSEMBLIES_DIR, exist_ok=True)

REF_ACC = "NC_014373.1"
REF_CDS_FILE = os.path.join(WORKSPACE, "bdbv_ref_cds.fasta")
FOREGROUND_LIST_FILE = os.path.join(WORKSPACE, "foreground_list.txt")

# 1. DOWNLOAD AND CONSTRUCT REFERENCE CDS FASTA
print(f"Step 1: Downloading Reference Genome {REF_ACC}...")
ref_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id={REF_ACC}&retmode=text&rettype=gb"
req = urllib.request.Request(ref_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    ref_gb_text = resp.read().decode('utf-8')

ref_record = SeqIO.read(io.StringIO(ref_gb_text), 'genbank')
ref_cds_records = []

# Standard genes to extract
target_genes = ["NP", "VP35", "VP40", "GP", "VP30", "VP24", "L"]
extracted_genes = set()

for feat in ref_record.features:
    if feat.type == 'CDS':
        gene = feat.qualifiers.get('gene', [''])[0]
        product = feat.qualifiers.get('product', [''])[0]
        
        # We want the structural GP (spike glycoprotein) which is the joined one (length 2031)
        if gene == "GP" and "spike glycoprotein" not in product.lower():
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

# 2. QUERY PATHOPLEXUS FOR METADATA
print("Step 2: Querying Pathoplexus for Bundibugyo ebolavirus genomes...")
lapis_url = "https://lapis.pathoplexus.org/ebola-bdbv/sample/details"
req = urllib.request.Request(lapis_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    metadata = json.loads(resp.read().decode())

samples = metadata.get('data', [])
print(f"Found {len(samples)} total BDBV records in Pathoplexus.")

# Filter for high-quality (length >= 18000, completeness >= 0.90) and group by accession (latest version)
latest_versions = {}
for s in samples:
    acc = s.get('accession')
    version = s.get('version', 1)
    length = s.get('length', 0)
    comp = s.get('completeness', 0.0)
    
    # Quality filter
    if length < 18000 or comp < 0.90:
        continue
        
    # Skip known duplicate sequence PP_006Y8S4
    if acc == 'PP_006Y8S4':
        continue
        
    if acc not in latest_versions or version > latest_versions[acc]['version']:
        latest_versions[acc] = s

print(f"Curated {len(latest_versions)} unique high-quality genomes.")

# Separate into Foreground (2026) and Background (pre-2026)
foreground_samples = {}
background_samples = {}

for acc, s in latest_versions.items():
    coll_date = s.get('sampleCollectionDate', '')
    if coll_date and '2026' in coll_date:
        foreground_samples[acc] = s
    else:
        background_samples[acc] = s

print(f"  Foreground (2026 Outbreak): {len(foreground_samples)} genomes")
print(f"  Background (Historical): {len(background_samples)} genomes")

# 3. DOWNLOAD FOREGROUND GENOMES
print("\nStep 3: Downloading foreground genomes...")
foreground_headers = []

for acc, s in sorted(foreground_samples.items()):
    country = s.get('geoLocCountry') or 'Unknown'
    country = country.replace(' ', '_').replace('(', '').replace(')', '')
    version = s.get('version', 1)
    coll_date = s.get('sampleCollectionDate', '2026')
    
    clean_name = f"{country}_{acc}_{version}_{coll_date}_foreground"
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)
    out_path = os.path.join(ASSEMBLIES_DIR, f"{clean_name}.fasta")
    foreground_headers.append(clean_name)
    
    if os.path.exists(out_path):
        print(f"  {clean_name}.fasta already exists. Skipping download.")
        continue
        
    seq_url = f"https://pathoplexus.org/seq/{acc}.fa"
    print(f"  Downloading {acc}...")
    try:
        seq_req = urllib.request.Request(seq_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(seq_req) as seq_resp:
            seq_text = seq_resp.read().decode('utf-8')
            
        parsed_seqs = list(SeqIO.parse(io.StringIO(seq_text), 'fasta'))
        if parsed_seqs:
            seq_record = parsed_seqs[0]
            seq_record.id = clean_name
            seq_record.name = ""
            seq_record.description = ""
            
            with open(out_path, "w") as out_f:
                SeqIO.write(seq_record, out_f, "fasta")
            print(f"    Saved: {clean_name}.fasta")
    except Exception as e:
        print(f"    Error downloading {acc}: {e}")

# Save foreground headers list
with open(FOREGROUND_LIST_FILE, "w") as f:
    f.write("\n".join(foreground_headers) + "\n")
print(f"Foreground list saved to {FOREGROUND_LIST_FILE}")

# 4. DOWNLOAD BACKGROUND GENOMES
print("\nStep 4: Downloading background genomes...")
for acc, s in sorted(background_samples.items()):
    country = s.get('geoLocCountry') or 'Unknown'
    country = country.replace(' ', '_').replace('(', '').replace(')', '')
    version = s.get('version', 1)
    coll_date = s.get('sampleCollectionDate', 'historical')
    if not coll_date or coll_date == 'None':
        coll_date = 'historical'
        
    clean_name = f"{country}_{acc}_{version}_{coll_date}_background"
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)
    out_path = os.path.join(ASSEMBLIES_DIR, f"{clean_name}.fasta")
    
    if os.path.exists(out_path):
        print(f"  {clean_name}.fasta already exists. Skipping download.")
        continue
        
    seq_url = f"https://pathoplexus.org/seq/{acc}.fa"
    print(f"  Downloading {acc}...")
    try:
        seq_req = urllib.request.Request(seq_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(seq_req) as seq_resp:
            seq_text = seq_resp.read().decode('utf-8')
            
        parsed_seqs = list(SeqIO.parse(io.StringIO(seq_text), 'fasta'))
        if parsed_seqs:
            seq_record = parsed_seqs[0]
            seq_record.id = clean_name
            seq_record.name = ""
            seq_record.description = ""
            
            with open(out_path, "w") as out_f:
                SeqIO.write(seq_record, out_f, "fasta")
            print(f"    Saved: {clean_name}.fasta")
    except Exception as e:
        print(f"    Error downloading {acc}: {e}")

print("\nData preparation complete!")
