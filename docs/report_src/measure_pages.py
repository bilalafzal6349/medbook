"""Find the page of every heading and caption in a PDF render of the report and write pages.json.
Usage: python measure_pages.py report.pdf  (then rebuild with build_report.js)."""
import json, re, subprocess, sys
from pathlib import Path

pdf = sys.argv[1]
n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout).group(1))
pages = [subprocess.run(["pdftotext", "-layout", "-f", str(i), "-l", str(i), pdf, "-"], capture_output=True, text=True).stdout
         for i in range(1, n + 1)]
lines = [[l.strip() for l in p.splitlines() if l.strip()] for p in pages]

def roman(k):
    out = ""
    for v, s in [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]:
        while k >= v:
            out += s; k -= v
    return out

result, body_start = {}, None
for i, ls in enumerate(lines):
    if "Chapter 1: Introduction" in ls:
        body_start = i; break
assert body_start is not None
def label(i):
    return str(i - body_start + 1) if i >= body_start else roman(i)   # pdf page 1 is the title page (no number), page 2 is i

src = Path(__file__).with_name("content.js").read_text(encoding="utf-8")
heads = ["Declaration", "Certificate of Approval", "Acknowledgements", "Abstract", "Table of Contents", "List of Figures", "List of Tables", "List of Abbreviations"]
start = 0
for h in heads:
    for i in range(start, body_start):
        if h in lines[i][:3]:
            result["h:" + h] = label(i); start = i + 1; break
cur = body_start
for i in range(body_start, n):
    for l in lines[i]:
        if re.match(r"^(Chapter \d+: .+|\d+\.\d+ .+|References|Appendix [A-Z]: .+)$", l) and not re.search(r"\.{3,}", l):
            result.setdefault("h:" + l, label(i))
        m = re.match(r"^((?:Figure|Table) \d+\.\d+):", l)
        if m:
            result.setdefault("c:" + m.group(1), label(i))
Path(__file__).with_name("pages.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
print(len(result), "entries; body starts at pdf page", body_start + 1)
