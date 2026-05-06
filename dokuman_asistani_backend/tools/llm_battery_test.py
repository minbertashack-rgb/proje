import argparse
import json
import re
import time
from llama_cpp import Llama


def clean_response(text: str) -> str:
    if not text:
        return ""

    # <think> ... </think> temizle
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Bazı modellerde kalabilen gereksiz boşluklar
    text = text.replace("\r\n", "\n").strip()

    return text


def build_tests():
    ortak_metin = """JWT tabanlı kimlik doğrulama sistemlerinde sunucu, kullanıcı giriş yaptıktan sonra imzalı bir token üretir ve istemci bu tokenı sonraki isteklerde gönderir. Token içinde kullanıcıya ait bazı bilgiler taşınabilir; ancak bu yapı, token içeriğinin şifreli olduğu anlamına gelmez. Güvenlik, büyük ölçüde signature bölümünün doğruluğuna ve token üretiminde kullanılan gizli anahtarın korunmasına bağlıdır. Eğer gizli anahtar ele geçirilirse saldırgan geçerli görünümlü tokenlar üretebilir. Bu nedenle JWT kullanımı performans avantajı sağlasa da anahtar yönetimi ve token süresi gibi ayarlar dikkatli yapılmalıdır."""

    turkce_kilit = """Sen Türkçe cevap veren bir doküman asistanısın.
Tüm cevapların yalnızca Türkçe olacak.
Sadece verilen metne dayanacaksın.
Metin dışında bilgi eklemeyeceksin.
Bilgi yetersizse bunu açıkça söyleyeceksin.
Format dışına çıkmayacaksın.
Gereksiz açıklama eklemeyeceksin."""

    return [
        {
    "name": "DOCVERSE_2_ZOR_SORU",
    "temperature": 0.1,
    "max_tokens": 320,
    "prompt": f"""{turkce_kilit}

Aşağıdaki metinden sadece 2 zor soru üret.

Kurallar:
- Doğrudan tanım sorma
- Sorular neden-sonuç, amaç, fark veya ilişki kurma gerektirsin
- Cevap yalnızca metinden çıkarılabilsin
- Sorular kolay veya normal seviye olmasın
- Her sorunun hemen altına kısa cevap yaz
- Başka açıklama ekleme
- Format dışına çıkma

Şu formatı aynen kullan:

1. ...
Cevap: ...

2. ...
Cevap: ...

Metin:
{ortak_metin}""",
},
        {
            "name": "DOCVERSE_KAVRAMLAR",
            "temperature": 0.1,
            "max_tokens": 260,
            "prompt": f"""{turkce_kilit}

Aşağıdaki metindeki en önemli 3 kavramı veya ifadeyi seç.
Yalnızca metne dayan.
Her birini kısa ve anlaşılır açıkla.

Şu formatı aynen kullan:

1) ...
Açıklama: ...

2) ...
Açıklama: ...

3) ...
Açıklama: ...

Metin:
{ortak_metin}""",
        },
        {
            "name": "DOCVERSE_KANITLI_CEVAP",
            "temperature": 0.0,
            "max_tokens": 220,
            "prompt": f"""{turkce_kilit}

Aşağıdaki soruya yalnızca verilen metne göre cevap ver.
Eğer cevap metinden çıkarılabiliyorsa cevap ver.
Eğer cevap metinde hiç yoksa sadece "Bu bilgi verilen metinde yok" yaz.
Tahmin yürütme.

Şu JSON formatını aynen koru:
{{"cevap":"...", "kanit":"...", "guven":"yuksek/orta/dusuk"}}

Kanıt alanına, cevabı destekleyen kısa cümleyi metinden yaz.

Metin:
{ortak_metin}

Soru:
Bu metnin ana fikri nedir?""",
        },
        {
            "name": "DOCVERSE_2_KOLAY_SORU",
            "temperature": 0.1,
            "max_tokens": 240,
            "prompt": f"""{turkce_kilit}

Aşağıdaki metinden sadece 2 kolay soru üret.
Sorular doğrudan metindeki bilgiye dayanacak.
Her sorunun hemen altına cevap yaz.
Başka açıklama ekleme.
Format dışına çıkma.

Şu formatı aynen kullan:

1. ...
Cevap: ...

2. ...
Cevap: ...

Metin:
{ortak_metin}""",
        },
        {
            "name": "DOCVERSE_2_NORMAL_SORU",
            "temperature": 0.1,
            "max_tokens": 260,
            "prompt": f"""{turkce_kilit}

Aşağıdaki metinden sadece 2 normal zorlukta soru üret.
Sorular metni anlamayı gerektirsin ama metin dışına çıkmasın.
Her sorunun hemen altına cevap yaz.
Başka açıklama ekleme.
Format dışına çıkma.

Şu formatı aynen kullan:

1. ...
Cevap: ...

2. ...
Cevap: ...

Metin:
{ortak_metin}""",
        },
        {
            "name": "DOCVERSE_2_ZOR_SORU",
            "temperature": 0.1,
            "max_tokens": 300,
            "prompt": f"""{turkce_kilit}

Aşağıdaki metinden sadece 2 zor soru üret.
Sorular ilişki kurma veya çıkarım gerektirsin.
Ama cevap yalnızca metinden çıkarılabilsin.
Her sorunun hemen altına cevap yaz.
Başka açıklama ekleme.
Format dışına çıkma.

Şu formatı aynen kullan:

1. ...
Cevap: ...

2. ...
Cevap: ...

Metin:
{ortak_metin}""",
        },
    ]


def run_test(llm, test_name, prompt, temperature, max_tokens):
    start = time.time()

    output = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    elapsed = time.time() - start

    raw_text = output["choices"][0]["message"]["content"]
    text = clean_response(raw_text)

    usage = output.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    print("\n" + "=" * 60)
    print(f"{test_name}  ({elapsed:.2f}s)  usage={usage}")
    print(text)

    return {
        "name": test_name,
        "elapsed_sec": round(elapsed, 2),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "response": text,
    }


def main():
    parser = argparse.ArgumentParser(description="GGUF model DocVerse battery test")
    parser.add_argument("--model", required=True, help="GGUF model path")
    parser.add_argument("--n_ctx", type=int, default=2048, help="Context size")
    parser.add_argument("--threads", type=int, default=6, help="CPU thread count")
    parser.add_argument("--gpu_layers", type=int, default=0, help="GPU layers")
    parser.add_argument("--save_json", default="", help="Optional output json file path")
    args = parser.parse_args()

    print(f"✅ Model: {args.model}")
    print(f"⚙️ n_ctx={args.n_ctx} threads={args.threads} gpu_layers={args.gpu_layers}")

    llm = Llama(
        model_path=args.model,
        n_ctx=args.n_ctx,
        n_threads=args.threads,
        n_gpu_layers=args.gpu_layers,
        verbose=False,
    )

    results = []
    for test in build_tests():
        results.append(
            run_test(
                llm=llm,
                test_name=test["name"],
                prompt=test["prompt"],
                temperature=test["temperature"],
                max_tokens=test["max_tokens"],
            )
        )

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Sonuçlar kaydedildi: {args.save_json}")


if __name__ == "__main__":
    main()