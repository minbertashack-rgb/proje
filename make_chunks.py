import os, json, glob

DOCS_DIR = "ml/data/docs"
OUT = "ml/data/chunks.jsonl"

MAX_CHARS = 1400
OVERLAP = 200

def chunk_text(text: str):
    text = text.replace("\r\n", "\n")
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + MAX_CHARS)
        chunk = text[i:j].strip()
        if chunk:
            chunks.append(chunk)
        i = j - OVERLAP
        if i < 0: i = 0
        if j == len(text): break
    return chunks

os.makedirs(os.path.dirname(OUT), exist_ok=True)

with open(OUT, "w", encoding="utf-8") as w:
    for path in glob.glob(os.path.join(DOCS_DIR, "*.txt")):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        base = os.path.splitext(os.path.basename(path))[0]
        for idx, ch in enumerate(chunk_text(text)):
            rec = {
                "doc_id": base,
                "chunk_id": f"{base}_c{idx:04d}",
                "text": ch
            }
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")

print("OK ->", OUT)