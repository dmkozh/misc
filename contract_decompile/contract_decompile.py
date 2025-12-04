#!/usr/bin/env python3

# Decompiles all Wasm files in CONTRACTS_DIR and fixes imports using WATs in WAT_DIR (decompilation may mess imports up).
# Also gives imports readable names using the env.json from GitHub.
# Requirements:
# - Get contracts from https://github.com/leighmcculloch/contract-wasms
# - wasm-decompile from WABT tool in PATH. Download WABT here: https://github.com/WebAssembly/wabt/releases

import json, re, subprocess, sys
from pathlib import Path
from urllib.request import urlopen

CONTRACTS_DIR = "contracts"
WAT_DIR = "wat"
OUTPUT_DIR = "decomp"

def fetch_json(url):
    if "github.com" in url and "/blob/" in url:
        url = url.replace("https://github.com", "https://raw.githubusercontent.com").replace("/blob/", "/")
    with urlopen(url) as r:
        return json.load(r)

def build_map(env):
    m = {}
    for mod in env.get("modules", []):
        mod_exp = mod.get("export")
        if not mod_exp: continue
        for fn in mod.get("functions", []):
            fn_exp = fn.get("export")
            name = fn.get("name")
            if fn_exp is None or name is None:
                raise SystemExit("function entry missing export or name")
            key = f"{mod_exp}{fn_exp}"
            m[key] = name
    return m

def decompile_all():
    for wasm in Path(CONTRACTS_DIR).glob("*.wasm"):
        out = Path(OUTPUT_DIR) / wasm.name
        out.parent.mkdir(parents=True, exist_ok=True)
        print("decompiling", wasm)
        with open(out, "wb") as f:
            subprocess.run(["wasm-decompile", str(wasm)], check=True, stdout=f)

def extract_decomp_imports(text):
    # capture names like: import function l_1(a:long, b:long):long; // func2
    return re.findall(r'\bimport function\s+([A-Za-z0-9_]+)\s*\(', text)

def extract_wat_imports(text):
    # capture pairs from lines like: (import "v" "1" (func (;2;) (type 0)))
    return re.findall(r'\(import\s+"([^"]+)"\s+"([^"]+)"', text)

def process_pairs(mapping):
    for decomp_file in Path(OUTPUT_DIR).glob("*.wasm"):
        name = decomp_file.stem
        wat_file = Path(WAT_DIR) / f"{name}.wat"
        if not wat_file.exists():
            raise SystemExit(f"missing wat for {name}")
        print("processing", name)
        decomp_text = decomp_file.read_text(encoding="utf-8")
        wat_text = wat_file.read_text(encoding="utf-8")

        decomp_imports = extract_decomp_imports(decomp_text)
        wat_imports = extract_wat_imports(wat_text)
        if len(decomp_imports) != len(wat_imports):
            raise SystemExit(f"import count mismatch in {name}: decomp={len(decomp_imports)} wat={len(wat_imports)}")

        for orig, (m1, m2) in zip(decomp_imports, wat_imports):
            key = f"{m1}{m2}"
            if key not in mapping:
                raise SystemExit(f"mapping not found for {key} (file {name})")
            new = mapping[key]
            # replace occurrences of " {orig}(" with " {new}("
            old_pat = f" {orig}("
            new_pat = f" {new}("
            if old_pat not in decomp_text:
                # it's possible import declaration at line start; also try start-of-line
                # but spec said strictly space before name, so treat absence as error
                raise SystemExit(f"expected ' {orig}(' in decomp {name} but not found")
            decomp_text = decomp_text.replace(old_pat, new_pat)

        decomp_file.write_text(decomp_text, encoding="utf-8")
        print("updated", decomp_file)

def main():
    env_url = "https://github.com/stellar/rs-soroban-env/blob/main/soroban-env-common/env.json"
    print("fetching env json")
    env = fetch_json(env_url)
    print("building mapping")
    mapping = build_map(env)
    print("decompiling wasm files")
    decompile_all()
    print("fixing decompiled imports")
    process_pairs(mapping)
    print("done")

if __name__ == "__main__":
    main()
