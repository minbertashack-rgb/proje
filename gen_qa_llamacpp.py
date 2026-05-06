import json, re, os, random
from llama_cpp import Llama

MODEL_PATH = r"C:\PATH\TO\DeepSeek-R1-Distill-Qwen-7B-Q6_K.gguf"  # <- bunu düzelt
CHUNKS = "ml/data/chunks.jsonl"
OUT_TRAIN = "ml/data/train.jsonl"
OUT_VAL = "ml/data/val.jsonl"

SYSTEM = (
  "Sen kanitli cevap veren asistansin. Sadece verilen CONTEXT'e dayan. "
  "Cevabin sonunda 'citations' alaninda kullandigin chunk_id listesini ver. "
  "Eger cevap CONTEXT'te yoksa aynen 'NOT_IN_DOC' yaz."
)

PROMPT_TMPL = """CONTEXT:
[{chunk_id}] {text}

Gorev:
1) Bu CONTEXT'ten 1 tane SORU uret (kisa ve net).
2) CEVAP mutlaka CONTEXT icinden kelime kelime bulunabilir olsun.
3) JSON olarak ver:
{{"question":"...","answer":"...","citations":["{chunk_id}"]}}
"""

def answer_in_chunk(answer: str, chunk: str) -> bool:
    if not answer or answer.strip().upper() == "NOT_IN_DOC":
        return True
    a = re.sub(r"\s+", " ", answer.strip())
    c = re.sub(r"\s+", " ", chunk)
    return a.lower() in c.lower()

llm = Llama(model_path=MODEL_PATH, n_ctx=4096, n_threads=8)

pairs = []
with open(CHUNKS, "r", encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        prompt = PROMPT_TMPL.format(chunk_id=rec["chunk_id"], text=rec["text"])
        out = llm.create_chat_completion(
            messages=[
                {"role":"system","content": SYSTEM},
                {"role":"user","content": prompt}
            ],
            temperature=0.3,
            max_tokens=512
        )
        content = out["choices"][0]["message"]["content"].strip()
        print("RAW OUTPUT:\n", content)
        raise SystemExit()
        # JSON yakala
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            continue
        try:
            obj = json.loads(m.group(0))
        except:
            continue

        q = (obj.get("question") or "").strip()
        a = (obj.get("answer") or "").strip()
        if not q or not a:
            continue

        if not answer_in_chunk(a, rec["text"]):
            continue

        ex = {
            "messages":[
              {"role":"system","content": SYSTEM},
              {"role":"user","content": f"CONTEXT:\n[{rec['chunk_id']}] {rec['text']}\n\nSoru: {q}"},
              {"role":"assistant","content": f"final: {a}\ncitations: [{rec['chunk_id']}]"}
            ]
        }
        pairs.append(ex)

print("Toplanan örnek:", len(pairs))

random.shuffle(pairs)
cut = int(len(pairs)*0.9)
train, val = pairs[:cut], pairs[cut:]

with open(OUT_TRAIN, "w", encoding="utf-8") as w:
    for ex in train:
        w.write(json.dumps(ex, ensure_ascii=False) + "\n")

with open(OUT_VAL, "w", encoding="utf-8") as w:
    for ex in val:
        w.write(json.dumps(ex, ensure_ascii=False) + "\n")

print("OK ->", OUT_TRAIN, OUT_VAL)