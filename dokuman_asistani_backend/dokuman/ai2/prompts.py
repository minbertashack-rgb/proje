"""AI2 istemleri icin kisa, guvenli ve goreve ozel prompt kuruculari."""

import json

from dokuman.services.quiz_runtime import build_mini_quiz_gate


def _looks_like_short_structured_piece(text: str) -> bool:
    """Kisa tablo/list/config benzeri parcalari prompt icinde ayri ele almak icin sezer."""
    clean = " ".join(str(text or "").split())
    if not clean or len(clean) > 100:
        return False
    return "|" in clean or "/" in clean or ";" in clean


def _profile_lines(tema: str, tarz: str, seviye: str, mesaj: str) -> list[str]:
    """Kullanici profilini prompt'a deterministik satirlar halinde ekler."""
    lines = [f"TEMA: {tema}", f"TARZ: {tarz}", f"SEVIYE: {seviye}"]
    if mesaj and mesaj.lower() not in {"bu kısmı daha basit anlat.", "bu kismi daha basit anlat.", "yok"}:
        lines.append(f"KULLANICI_NOTU: {mesaj}")
    return lines


def _piece_class(text: str) -> str:
    """Parca uzunlugunu prompt limitleri ve ton secimi icin kaba siniflara ayirir."""
    clean = " ".join(str(text or "").split())
    if not clean:
        return "bos"
    if _looks_like_short_structured_piece(clean) or len(clean) <= 240:
        return "kisa"
    if len(clean) <= 700:
        return "orta"
    return "uzun"


def _chunk_limit(piece_class: str) -> int:
    """Parca sinifina gore prompt'a alinacak metin tavanini belirler."""
    if piece_class == "kisa":
        return 280
    if piece_class == "orta":
        return 560
    return 760


def _clip_user_note(mesaj: str, limit: int = 140) -> str:
    """Uzun kullanici notunu prompt enjeksiyonu riskini buyutmeden kirpar."""
    clean = " ".join(str(mesaj or "").split()).strip()
    if len(clean) <= limit:
        return clean
    short = clean[:limit].rsplit(" ", 1)[0].strip()
    return short or clean[:limit].strip()


def _prompt_chunk_text(chunk_text: str, *, preserve_lines: bool = False) -> str:
    """Prompt'a girecek chunk metnini tek satir veya line-aware formda normalize eder."""
    raw = str(chunk_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not preserve_lines:
        return " ".join(raw.split()).strip()
    return "\n".join(line.rstrip() for line in raw.split("\n")).strip()


def _content_focus_lines(profile: dict) -> list[str]:
    """Parca tipine gore modele verilecek en kritik odak ipuclarini uret."""
    kind = " ".join(str(profile.get("chunk_kind") or "").split()).strip().lower()
    title = " ".join(str(profile.get("chunk_title") or "").split()).strip()
    code_subtype = " ".join(str(profile.get("code_subtype") or "").split()).strip().lower()
    language = " ".join(str(profile.get("language") or "").split()).strip()
    code_unit_kind = " ".join(str(profile.get("code_unit_kind") or "").split()).strip().lower()
    test_step_kind = " ".join(str(profile.get("test_step_kind") or "").split()).strip().lower()
    purpose_hints = [str(item).strip() for item in list(profile.get("code_purpose_hints") or []) if str(item).strip()]
    line_start = int(profile.get("line_start") or 0)
    line_end = int(profile.get("line_end") or 0)
    line_window = ""
    if line_start and line_end and line_end >= line_start:
        line_window = f"Satir araligi {line_start}-{line_end}."
    elif line_start:
        line_window = f"Satir araligi {line_start}."
    if kind == "table":
        return [
            "IPUCU: Bu parca tablo/Excel parcasi gibi davranabilir.",
            "IPUCU: one_liner ve very_simple alanlarinda tablo ne gosteriyor, hangi sutunlar onemli ve gorulen iliski ne bunu kisa anlat.",
        ]
    if kind == "code":
        title_line = f"IPUCU: Kod odagi '{title}'." if title else "IPUCU: Bu parca kod aciklamasi istiyor."
        language_line = f"IPUCU: Dil/format {language}." if language else ""
        unit_line = f"IPUCU: code_unit_kind={code_unit_kind}." if code_unit_kind else ""
        step_line = f"IPUCU: test_step_kind={test_step_kind}." if test_step_kind else ""
        hint_line = f"IPUCU: purpose_hints={', '.join(purpose_hints[:4])}." if purpose_hints else ""
        lines = [
            title_line,
            language_line,
            unit_line,
            step_line,
            hint_line,
            f"IPUCU: {line_window}" if line_window else "",
            "IPUCU: Dosya/fonksiyon/sinif amaci, kritik isimler ve veri akisina odaklan; kodda gorunmeyen davranisi uydurma.",
            "IPUCU: steps ve examples alanlarinda satir/blok uyumlu aciklama ver; genel gecme.",
            "IPUCU: function_purpose ana amaci, flow_summary girdiden sonuca akisi, block_comments blok mantigini, line_comments ise sadece anlamli satirlari kisa ve somut aciklasin.",
            "IPUCU: 'kontrol eder', 'bir sey yapar', 'veriyi isler' gibi genel fiiller tek basina yetmez; nesneyi ve amaci birlikte soyle.",
        ]
        if code_subtype in {"api_test", "test"}:
            lines.extend(
                [
                    "IPUCU: Test kodunda hazirlik, input, cagri, dogrulama ve beklenen sonucu ayir.",
                    "IPUCU: Assertion varsa neden yapildigini acikla; status assert, alan assert ve final state assert farkini karistirma.",
                ]
            )
            if language == "python":
                lines.extend(
                    [
                        "IPUCU: Python testinde arrange/act/assert sirasi korunabiliyorsa koru; monkeypatch/mock satirlarini hazirlik adimi olarak yorumla.",
                        "IPUCU: code_unit_kind veya test_step_kind verilmisse yorum tonunu buna gore netlestir; test_step_kind=setup ise hazirlik, assertion ise dogrulama dilini one cikar.",
                        "IPUCU: line_comments icinde yetki (force_authenticate), payload, endpoint cagrisi (client.post vb.), status assertion (HTTP 200/201 vb.), field assertion ve final state assertion zincirini kisa ve net yaz.",
                        "IPUCU: assert satirlarinda sadece 'kontrol eder' deme; neyi neden dogruladigini (ornegin HTTP 201 dondugunu veya beklenen alanin uretildigini) kisa ve net acikla.",
                        "IPUCU: Helper call + assertion veya chained assert varsa bunlari tek cumleye toplama; her anlamli satir veya kisa blok icin ayri neden-sonuc aciklamasi ver.",
                    ]
                )
        elif code_subtype == "sql":
            lines.extend(
                [
                    "IPUCU: SQL ise SELECT, FROM/JOIN, WHERE, GROUP BY ve ORDER BY akislarini ayir; write query ise hedef tablo ve etkisini kisa anlat.",
                    "IPUCU: Sorguda gorunmeyen tablo semasi veya veri sonucu uydurma.",
                    "IPUCU: CTE, subquery veya window function varsa sadece gorunen clause iliskisini anlat; motor davranisi veya sonuc seti uydurma.",
                ]
            )
        elif code_subtype == "config":
            lines.extend(
                [
                    "IPUCU: JSON/YAML/config ise section/group ile key-value satirlarini ayir.",
                    "IPUCU: Bu config alani neyi kontrol ediyor sorusuna sadece anahtar adlari ve gorunen degerler kadar cevap ver; baglanti, guvenlik, servis veya esik/deger tipini varsa belirt.",
                    "IPUCU: YAML anchor/alias veya multiline deger varsa sadece gorunen yapisal baglanti kadar konus; ortamsal anlam uydurma.",
                ]
            )
        elif code_subtype == "markup":
            lines.extend(
                [
                    "IPUCU: HTML/markup ise hangi yapisal bloklarin kuruldugunu anlat; form, section, input gibi etiketleri ayir ve varsa script/style bloklarini ayrica adlandir.",
                    "IPUCU: Markup'tan script davranisi uydurma.",
                    "IPUCU: Template syntax veya framework directive gorursen sadece gorunen baglama kadar acikla; render zamani veri uydurma.",
                ]
            )
        elif code_subtype in {"style", "script"}:
            lines.extend(
                [
                    "IPUCU: CSS/style ise secici ve gorunum etkisini; script ise event/handler, callback, API/DOM akislarini ayir.",
                    "IPUCU: Gorulen kural veya komut disinda hayali UI sonucu uydurma.",
                ]
            )
        elif code_subtype == "frontend":
            lines.extend(
                [
                    "IPUCU: Frontend ise input/event, handler, state veya API cagrisi ve render sonucunu ayir.",
                    "IPUCU: JS/TS callback veya nested method varsa parent-child iliskisini ve hangi adimin kimi tetikledigini belirt.",
                    "IPUCU: UI etkisini kodda gorulen state/call baglantisina dayandir; hayali ekran davranisi uydurma.",
                ]
            )
        elif code_subtype == "shell":
            lines.extend(
                [
                    "IPUCU: shell/ps1 ise function, variable, command, api_call ve control_flow adimlarini ayir.",
                    "IPUCU: Komut adlarini bos birakma; gorunen dis komut, endpoint degiskeni ve pipeline sirasini isim vererek acikla.",
                    "IPUCU: Ortamda ne oldugunu bilmiyorsan komutun sonucunu kesinlestirme; sadece gorunen komut amacini acikla.",
                    "IPUCU: Pipeline, subshell veya ileri PowerShell sozdizimi varsa sadece gorunen veri akisina kadar konus; yan etkileri kesinlestirme.",
                ]
            )
        elif code_subtype == "class":
            lines.extend(
                [
                    "IPUCU: Sinif ise kurulum, state ve metod sorumluluklarini ayir.",
                    "IPUCU: Sinif sorumlulugu, metod amaci ve state degisimini tutarli sekilde acikla ('Bu sinif su sorumlulugu tasir', 'Bu method nesnenin state'ini gunceller' gibi).",
                    "IPUCU: self.x = y gibi satirlarda yalnizca atama demek yerine bunun ilk durum mu yoksa anlamli bir state degisimi mi oldugunu belirt.",
                ]
            )
        elif code_subtype in {"function", "method"}:
            lines.extend(
                [
                    "IPUCU: Fonksiyon ise input, ana islem (veri donusumu veya kosul) ve return (donus) adimlarini daha belirgin hale getir.",
                    "IPUCU: Aciklamalarda 'Bu fonksiyon input(girdi) alir, ana islemi yapar ve sonucu dondurur' netligini kullan.",
                    "IPUCU: Helper call varsa bunu ara islem olarak ayir; girdi -> helper sonucu -> kosul -> return akisini genellemeden yaz.",
                    "IPUCU: line_comments yalniz anlamli donusum, kosul, state degisimi veya return satirlarini aciklasin; trivial satirlari doldurma.",
                    "IPUCU: Nested if/loop varsa genel gecme; hangi kosulun veya iterasyonun sonucu degistirdigini flow_summary ve block_comments icinde ayri goster.",
                ]
            )
            if code_subtype == "method":
                lines.extend(
                    [
                        "IPUCU: Method ise nesnenin state'ini okuma/guncelleme acisini ayrica belirt; input ile state arasindaki iliskiyi kisa ve dogal anlat.",
                        "IPUCU: self.x = y satirlarinda bunun ilk durum mu yoksa anlamli bir state degisimi mi oldugunu baglama gore ayir.",
                    ]
                )
        else:
            lines.extend(
                [
                    "IPUCU: JS/TS ise callback, nested function ve kontrol blogunu birbirine karistirma; parent unit bilgisini kullan.",
                    "IPUCU: Fonksiyon veya blok ise girdi, islem ve cikti adimlarini netlestir; 'Bu blok veriyi hazirlayip sonraki adima tasir' formunu koru.",
                ]
            )
        return [item for item in lines if item]
    if kind == "presentation":
        title_line = f"IPUCU: Slayt basligi '{title}'." if title else "IPUCU: Bu parca bir slayt/sunum parcasi olabilir."
        return [
            title_line,
            "IPUCU: Slaytin ana mesaji, onemli maddeleri ve varsa karisan noktayi kisa ve net acikla.",
        ]
    if kind == "visual":
        return [
            "IPUCU: Bu parca OCR veya gorsel cikisi olabilir.",
            "IPUCU: Once ana mesaji soyle, sonra gorulen metni sadece destek ipucu olarak kullan.",
        ]
    return [
        "IPUCU: Paragrafin ana fikrini, neden onemli oldugunu ve karisabilecek noktayi sade sekilde anlat.",
    ]


def build_kanitli_prompt(
    question: str,
    evidence: list[dict],
    *,
    allowed_citation_ids: list[int] | None = None,
    strict_evidence: bool = True,
    language_instruction: str = "",
) -> list[dict]:
    """Kanitli cevap icin allowlist ve evidence odakli prompt ciftini kurar."""
    clean_allowed_ids: list[int] = []
    seen_allowed_ids = set()
    for value in allowed_citation_ids or []:
        try:
            clean = int(value)
        except Exception:
            continue
        if clean in seen_allowed_ids:
            continue
        seen_allowed_ids.add(clean)
        clean_allowed_ids.append(clean)

    strict_flag = "true" if strict_evidence else "false"
    allowed_ids_json = json.dumps(clean_allowed_ids, ensure_ascii=False)

    sys = "\n".join(
        [
            "Sen DocVerse 'Kanitli Cevap' motorusun.",
            str(language_instruction or "").strip(),
            f"STRICT_EVIDENCE_MODE={strict_flag}",
            "SADECE verilen EVIDENCE parcalarina dayanarak cevap ver.",
            "EVIDENCE'da yoksa acikca: 'Dokumanda gecmiyor.' de.",
            "Asla uydurma yapma.",
            "Cikis SADECE JSON olacak.",
            'JSON sema: {"answer": string, "supported": boolean, "citations": [parca_id...], "missing": [string...], "followups": [string...]}',
            f"ALLOWED_CITATION_IDS={allowed_ids_json}",
            "Kurallar:",
            "- citations sadece ALLOWED_CITATION_IDS listesinden secilebilir.",
            "- Eger EVIDENCE yetersizse supported=false ve citations=[] olmali.",
            "- answer alani sadece citations ile dayandirabildigin iddialari icermeli.",
            "- Kaynak zayif veya kismi ise emin konusma; answer icinde bunu acikca belirt.",
            "- Tek bir parcaya dayaniyorsan cevabi o parcada acikca gorulen bilgiyle sinirla; genelleme yapma.",
            "- citations icinde tekrar eden id yazma ve citations disi hicbir kaynaga atif yapma.",
            "- ALLOWED_CITATION_IDS disindaki parca_id, kanit_id, sayfa, adres veya harici bilgi sizdirma.",
            "- EVIDENCE disindaki onceki bilgi, genel dunya bilgisi, egitim verisi veya tahmini bilgi kullanma.",
            "- Cok kritik: supported=true ise citations en az 1 id icermeli.",
            "- citations veremiyorsan supported=false ve answer='Dokumanda gecmiyor.' yaz.",
            "- unsupported_reason veya coverage_note eklersen onlar da sadece verilen EVIDENCE'a dayansin.",
            "JSON disinda tek karakter bile yazma.",
        ]
    )

    evidence_blocks = []
    for idx, item in enumerate(evidence or [], start=1):
        parca_id = item.get("parca_id")
        addr = " ".join(str(item.get("addr") or "").split()).strip()
        text = " ".join(str(item.get("text") or "").split()).strip()[:900]
        evidence_blocks.append(
            "\n".join(
                [
                    f"[{idx}] parca_id={parca_id}",
                    f"addr={addr}",
                    f"text={text}",
                ]
            )
        )

    user = "\n".join(
        [
            f"SORU: {' '.join(str(question or '').split()).strip()}",
            f"ALLOWED_CITATION_IDS={allowed_ids_json}",
            "EVIDENCE:",
            "\n\n".join(evidence_blocks) if evidence_blocks else "- yok -",
            "Cevabi sadece bu evidence listesinden kur ve sadece JSON don.",
        ]
    )

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]


def _anlamadim_requested_fields(profile: dict) -> tuple[list[str], int]:
    """Prompt'ta istenecek alanlari ve acceptance icin beklenen sayiyi hesaplar."""
    clean_profile = dict(profile or {})
    chunk_kind = " ".join(str(clean_profile.get("chunk_kind") or "").split()).strip().lower()
    mini_quiz_aktif = bool(clean_profile.get("mini_quiz_aktif", True))
    fields = ["one_liner", "very_simple", "glossary", "steps", "examples", "trap"]
    counted = list(fields)
    if chunk_kind == "code":
        code_fields = ["function_purpose", "flow_summary", "block_comments", "line_comments"]
        fields.extend(code_fields)
        counted.extend(code_fields)
    if mini_quiz_aktif:
        fields.append("mini_quiz")
        counted.append("mini_quiz")
    fields.append("dokumanda_yok")
    return fields, len(counted)


def _clip_prompt_text(chunk_text: str, *, limit: int, preserve_lines: bool) -> tuple[str, bool]:
    """Prompt metnini sinira gore kirpar ve kirpilip kirpilmadigini doner."""
    raw = _prompt_chunk_text(chunk_text, preserve_lines=preserve_lines)
    if len(raw) <= limit:
        return raw, False
    clipped = raw[:limit].rstrip()
    if preserve_lines:
        return f"{clipped}\n...", True
    return f"{clipped} ...", True


def build_anlamadim_prompt(
    addr: str,
    chunk_text: str,
    parca_id: int,
    profile: dict | None = None,
    *,
    return_meta: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Parca aciklama hattinin acceptance beklentilerine uygun promptu kur."""
    profile = dict(profile or {})
    tema = " ".join(str(profile.get("tema") or "genel").split()).strip() or "genel"
    tarz = " ".join(str(profile.get("tarz") or "adim_adim").split()).strip() or "adim_adim"
    seviye = " ".join(str(profile.get("seviye") or "orta").split()).strip() or "orta"
    mesaj = _clip_user_note(profile.get("mesaj") or "")
    quality_score = float(profile.get("quality_score") or 0.0)
    difficulty_score = float(profile.get("difficulty_score") or 0.0)
    weak_content = bool(profile.get("weak_content"))
    chunk_kind = " ".join(str(profile.get("chunk_kind") or "").split()).strip().lower()
    preserve_lines = chunk_kind == "code"
    language_instruction = " ".join(str(profile.get("language_instruction") or "").split()).strip()

    if "mini_quiz_aktif" in profile:
        mini_quiz_aktif = bool(profile.get("mini_quiz_aktif"))
    else:
        quiz_gate = build_mini_quiz_gate(
            text=str(chunk_text or ""),
            quality_score=quality_score,
            difficulty_score=difficulty_score,
            weak_content=weak_content,
        )
        mini_quiz_aktif = bool(quiz_gate.get("quiz_eligible"))
    profile["mini_quiz_aktif"] = mini_quiz_aktif

    parca_sinifi = _piece_class(chunk_text)
    clipped_text, prompt_kisaltildi_mi = _clip_prompt_text(
        chunk_text,
        limit=_chunk_limit(parca_sinifi),
        preserve_lines=preserve_lines,
    )
    fields, istenen_alan_sayisi = _anlamadim_requested_fields(profile)
    focus_lines = _content_focus_lines(profile)
    preference_prompt = "\n".join(str(profile.get("preference_prompt") or "").splitlines()).strip()

    system_lines = [
        "Sen DocVerse 'Anlamadim' aciklama motorusun.",
        language_instruction,
        "Sadece verilen METIN ve profil ipuclarina dayanarak acikla.",
        "Kodda, tabloda veya parcada gorunmeyen davranis, sema, veri veya sonuc uydurma.",
        "Cikis SADECE JSON olacak.",
        f"Alanlar: {', '.join(fields)}.",
        'JSON kurali: glossary icin [{"terim":"...","tanim":"..."}], steps/examples icin string listesi don.',
        "steps ve examples alanlarini parcaya bagli, somut ve kisa tut.",
        "one_liner ve very_simple alanlarina sadece baslik numarasi, sayi veya noktalama yazma.",
        "'2.', '1.', '3', '-', '.', 'Nedir?' gibi kisa/anlamsiz degerleri cevap olarak kullanma.",
        "examples alaninda 'Gundelik dilde: 2.' gibi baslik numarasindan turetilmis ornek yazma.",
        "dokumanda_yok sadece parca gercekten anlamsizsa veya aciklama kurulamiyorsa true olsun.",
    ]
    if mini_quiz_aktif:
        system_lines.append('mini_quiz alani [{"q":"...","a":"..."}] seklinde 3 kisa soru-cevap icersin; cevap kaynak cumleyi aynen tekrar etmesin.')
    if chunk_kind == "code":
        system_lines.append("Kod parcalarinda function_purpose, flow_summary, block_comments ve line_comments alanlarini da doldur.")
        system_lines.append("block_comments blok seviyesinde, line_comments ise satir seviyesinde somut aciklamalar icersin.")
    if preference_prompt:
        system_lines.append(preference_prompt)

    user_lines = [
        f"ADRES: {addr}",
        f"PARCA_ID: {int(parca_id)}",
        *_profile_lines(tema, tarz, seviye, mesaj),
    ]
    chunk_title = " ".join(str(profile.get("chunk_title") or "").split()).strip()
    if chunk_title:
        user_lines.append(f"PARCA_BASLIGI: {chunk_title}")
    if chunk_kind:
        user_lines.append(f"PARCA_TURU: {chunk_kind}")
    if quality_score:
        user_lines.append(f"QUALITY_SCORE: {quality_score:.2f}")
    if difficulty_score:
        user_lines.append(f"DIFFICULTY_SCORE: {difficulty_score:.2f}")
    if weak_content:
        user_lines.append("UYARI: parca weak_content olarak isaretli; gorunen metni asma.")
    user_lines.extend(focus_lines)
    user_lines.extend(
        [
            "METIN:",
            clipped_text,
            "Sadece JSON don.",
        ]
    )

    messages = [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": "\n".join(user_lines)},
    ]
    meta = {
        "parca_metin_uzunlugu": len(str(chunk_text or "")),
        "prompt_parca_metin_uzunlugu": len(clipped_text),
        "prompt_kisaltildi_mi": prompt_kisaltildi_mi,
        "istenen_alan_sayisi": istenen_alan_sayisi,
        "kisa_parca_mi": parca_sinifi == "kisa",
        "parca_sinifi": parca_sinifi,
        "agir_prompt_suphesi": bool(prompt_kisaltildi_mi or (chunk_kind == "code" and istenen_alan_sayisi >= 11)),
        "mini_quiz_aktif": mini_quiz_aktif,
    }
    if return_meta:
        return messages, meta
    return messages
