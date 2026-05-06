from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.ai2_runtime import DEFAULT_ALIAS, DEFAULT_BASE_URL, DEFAULT_MODEL, ensure_ai2_ready


def _repo_root() -> Path:
    return REPO_ROOT


def _load_auth(auth_path: Path) -> dict:
    with auth_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _json_request(url: str, payload: dict, headers: dict | None = None, method: str = "POST", timeout: int = 120) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_token(base_url: str, username: str, password: str) -> str:
    out = _json_request(
        f"{base_url.rstrip('/')}/api/kimlik/token/",
        {"username": username, "password": password},
        timeout=60,
    )
    token = out.get("access") or ""
    if not token:
        raise RuntimeError("JWT access token alinamadi.")
    return token


def _setup_django():
    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dokuman_asistani.settings")
    import django

    django.setup()


def _call_endpoint_internal(username: str, parca_id: int, payload: dict) -> dict:
    _setup_django()
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    user = get_user_model().objects.get(username=username)
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        f"/api/dokuman-asistani/parcalar/{parca_id}/anlamadim-v2/",
        payload,
        format="json",
    )
    if response.status_code >= 400:
        raise RuntimeError(f"internal_http_{response.status_code}")
    return response.json()


def _pick_samples(username: str, limit: int, max_chars: int) -> list[dict]:
    _setup_django()
    from dokuman.models import Parca

    qs = list(
        Parca.objects.select_related("dokuman__owner")
        .filter(dokuman__owner__username=username)
        .order_by("-id")
    )

    qs.sort(key=lambda parca: (len((parca.metin or "").strip()), -int(parca.id)))

    preferred_patterns = [
        "txt:", "docx:", "pdf:", "xlsx:", "pptx:", "0", "1", "1.1",
    ]

    picked = []
    seen_texts = set()
    for pattern in preferred_patterns:
        for parca in qs:
            text = (parca.metin or "").strip()
            if not text or len(text) < 8:
                continue
            if len(text) > max_chars:
                continue
            if pattern not in (parca.adres or ""):
                continue
            fingerprint = re.sub(r"\s+", " ", text.lower())[:140]
            if fingerprint in seen_texts:
                continue
            seen_texts.add(fingerprint)
            picked.append(
                {
                    "id": parca.id,
                    "adres": parca.adres or "",
                    "dokuman": getattr(parca.dokuman, "baslik", "") or "",
                    "metin": text,
                }
            )
            if len(picked) >= limit:
                return picked

    for parca in qs:
        text = (parca.metin or "").strip()
        if not text or len(text) < 8:
            continue
        if len(text) > max_chars:
            continue
        fingerprint = re.sub(r"\s+", " ", text.lower())[:140]
        if fingerprint in seen_texts:
            continue
        seen_texts.add(fingerprint)
        picked.append(
            {
                "id": parca.id,
                "adres": parca.adres or "",
                "dokuman": getattr(parca.dokuman, "baslik", "") or "",
                "metin": text,
            }
        )
        if len(picked) >= limit:
            break

    return picked


def _is_surface_glossary(glossary: list[dict]) -> bool:
    if not glossary:
        return True
    weak_phrases = ("metindeki teknik terim", "kavrami ana fikirle baglantili", "teknik terim/kisaltma")
    for item in glossary:
        definition = str(item.get("tanim") or "").strip().lower()
        if len(definition) < 12:
            return True
        if any(p in definition for p in weak_phrases):
            return True
    return False


def _is_weak_list(items: list[str], *, min_count: int, min_len: int = 12) -> bool:
    if len(items) < min_count:
        return True
    return any(len(str(item).strip()) < min_len for item in items[:min_count])


def _is_repetitive_quiz(items: list[dict]) -> bool:
    if len(items) < 3:
        return True
    questions = [str(item.get("q") or "").strip().lower() for item in items]
    if len(set(questions)) < len(questions):
        return True
    if any(len(q) < 10 for q in questions):
        return True
    return False


def _piece_kind(text: str, adres: str) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    cells = [part.strip() for part in re.split(r"\s*(?:\||/|;)\s*", clean) if part.strip()]
    if cells and len(cells) >= 2:
        if all(re.fullmatch(r"[\d.,:%+-]+", cell) for cell in cells):
            return "numeric_row"
        if all(re.fullmatch(r"[A-ZÇĞİÖŞÜ0-9_]{3,16}", cell) for cell in cells):
            return "header_row"
        if any(cell.upper() in {"IF", "XLOOKUP", "JWT", "RLS", "SQL", "API"} for cell in cells):
            return "technical_label_row"
        return "structured_short"
    if clean.endswith("..."):
        return "clipped_note"
    if "select " in clean.lower():
        return "technical_sql_note"
    if len(clean) <= 36:
        return "very_short_note"
    if adres.startswith("pdf:"):
        return "pdf_text"
    if adres.startswith("docx:"):
        return "docx_text"
    if adres.startswith("xlsx:"):
        return "xlsx_text"
    return "plain_text"


def _contains_doc_terms(text: str, candidate: str) -> bool:
    source_words = set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", text.lower()))
    cand_words = [w for w in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", candidate.lower()) if len(w) >= 4]
    digit_hits = set(re.findall(r"\b\d+\b", candidate)) & set(re.findall(r"\b\d+\b", text))
    label_hits = set(re.findall(r"\b[A-ZÇĞİÖŞÜ0-9_]{3,16}\b", candidate)) & set(re.findall(r"\b[A-ZÇĞİÖŞÜ0-9_]{3,16}\b", text))
    if digit_hits or label_hits:
        return True
    if not cand_words:
        return False
    return sum(1 for w in cand_words if w in source_words) >= 1


def _evaluate_case(case: dict, response: dict) -> dict:
    text = case["metin"]
    kind = _piece_kind(text, case["adres"])
    one_liner = str(response.get("one_liner") or "").strip()
    very_simple = str(response.get("very_simple") or "").strip()
    glossary = response.get("glossary") if isinstance(response.get("glossary"), list) else []
    steps = response.get("steps") if isinstance(response.get("steps"), list) else []
    examples = response.get("examples") if isinstance(response.get("examples"), list) else []
    trap = str(response.get("trap") or "").strip()
    mini_quiz = response.get("mini_quiz") if isinstance(response.get("mini_quiz"), list) else []
    dokumanda_yok = bool(response.get("dokumanda_yok", False))

    problems = []

    if dokumanda_yok and len(text) >= 18:
        problems.append("false_dokumanda_yok")
    if len(one_liner) < 18 or not _contains_doc_terms(text, one_liner):
        problems.append("weak_one_liner")
    if len(very_simple) < 24 or not _contains_doc_terms(text, very_simple):
        problems.append("weak_very_simple")
    if _is_surface_glossary(glossary):
        problems.append("weak_glossary")
    if _is_weak_list(steps, min_count=2, min_len=14):
        problems.append("weak_steps")
    if _is_weak_list(examples, min_count=1, min_len=14):
        problems.append("weak_examples")
    if len(trap) < 16:
        problems.append("weak_trap")
    if _is_repetitive_quiz(mini_quiz):
        problems.append("weak_mini_quiz")

    score = 7 - len({p for p in problems if p.startswith("weak_") or p == "false_dokumanda_yok"})

    return {
        "parca_id": case["id"],
        "adres": case["adres"],
        "dokuman": case["dokuman"],
        "piece_kind": kind,
        "snippet": text[:180],
        "dokumanda_yok": dokumanda_yok,
        "score": max(0, score),
        "problems": problems,
        "response": {
            "one_liner": one_liner,
            "very_simple": very_simple,
            "glossary_count": len(glossary),
            "steps_count": len(steps),
            "examples_count": len(examples),
            "trap": trap,
            "mini_quiz_count": len(mini_quiz),
        },
    }


def _transport_note(transport: str) -> str:
    if transport == "internal":
        return "internal transport Django icinde DRF APIClient kullanir; AI2 yine canli 8002 uzerinden cagrilir."
    return "http transport Django dev-server uzerinden gider; dev-server katmaninda baglanti kararsizligi gorulebilir."


def _build_summary(results: list[dict], problem_counter: Counter, transport: str, ai2_status: dict) -> dict:
    durations = [float(item.get("response_sec", 0.0) or 0.0) for item in results]
    avg_score = round(sum(item["score"] for item in results) / max(1, len(results)), 2)
    avg_response = round(sum(durations) / max(1, len(durations)), 2)
    piece_kind_counts = Counter(str(item.get("piece_kind") or "unknown") for item in results)
    by_kind: dict[str, list[float]] = {}
    for item in results:
        by_kind.setdefault(str(item.get("piece_kind") or "unknown"), []).append(float(item.get("response_sec", 0.0) or 0.0))
    avg_by_kind = {kind: round(sum(vals) / max(1, len(vals)), 2) for kind, vals in by_kind.items()}
    slowest_kinds = sorted(avg_by_kind.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "sample_count": len(results),
        "total_piece_count": len(results),
        "toplam_parca": len(results),
        "avg_score": avg_score,
        "ortalama_skor": avg_score,
        "problem_counts": dict(problem_counter),
        "weak_one_liner_count": int(problem_counter.get("weak_one_liner", 0)),
        "weak_very_simple_count": int(problem_counter.get("weak_very_simple", 0)),
        "false_dokumanda_yok_count": int(problem_counter.get("false_dokumanda_yok", 0)),
        "weak_glossary_count": int(problem_counter.get("weak_glossary", 0)),
        "weak_steps_count": int(problem_counter.get("weak_steps", 0)),
        "weak_examples_count": int(problem_counter.get("weak_examples", 0)),
        "weak_mini_quiz_count": int(problem_counter.get("weak_mini_quiz", 0)),
        "weak_one_liner": int(problem_counter.get("weak_one_liner", 0)),
        "weak_very_simple": int(problem_counter.get("weak_very_simple", 0)),
        "weak_glossary": int(problem_counter.get("weak_glossary", 0)),
        "weak_steps": int(problem_counter.get("weak_steps", 0)),
        "weak_examples": int(problem_counter.get("weak_examples", 0)),
        "weak_mini_quiz": int(problem_counter.get("weak_mini_quiz", 0)),
        "false_dokumanda_yok": int(problem_counter.get("false_dokumanda_yok", 0)),
        "avg_response_sec": avg_response,
        "ortalama_cevap_suresi": avg_response,
        "max_response_sec": round(max(durations) if durations else 0.0, 2),
        "min_response_sec": round(min(durations) if durations else 0.0, 2),
        "total_response_sec": round(sum(durations), 2),
        "min_cevap_suresi": round(min(durations) if durations else 0.0, 2),
        "max_cevap_suresi": round(max(durations) if durations else 0.0, 2),
        "parca_tipi_dagilimi": dict(piece_kind_counts),
        "avg_response_by_piece_kind": avg_by_kind,
        "slowest_piece_kinds": slowest_kinds,
        "transport_turu": transport,
        "ai2_hazirlik_durumu": dict(ai2_status or {}),
    }


def _readable_summary(summary: dict) -> str:
    slowest = ", ".join(f"{kind}={value}s" for kind, value in summary.get("slowest_piece_kinds", [])) or "yok"
    piece_counts = ", ".join(f"{kind}={count}" for kind, count in sorted((summary.get("parca_tipi_dagilimi") or {}).items())) or "yok"
    return "\n".join(
        [
            f"toplam_parca: {summary.get('toplam_parca', 0)}",
            f"ortalama_skor: {summary.get('ortalama_skor', 0)}",
            f"ortalama_cevap_suresi: {summary.get('ortalama_cevap_suresi', 0)}s",
            f"min_cevap_suresi: {summary.get('min_cevap_suresi', 0)}s",
            f"max_cevap_suresi: {summary.get('max_cevap_suresi', 0)}s",
            f"weak_one_liner: {summary.get('weak_one_liner', 0)}",
            f"weak_very_simple: {summary.get('weak_very_simple', 0)}",
            f"weak_glossary: {summary.get('weak_glossary', 0)}",
            f"weak_steps: {summary.get('weak_steps', 0)}",
            f"weak_examples: {summary.get('weak_examples', 0)}",
            f"weak_mini_quiz: {summary.get('weak_mini_quiz', 0)}",
            f"false_dokumanda_yok: {summary.get('false_dokumanda_yok', 0)}",
            f"parca_tipi_dagilimi: {piece_counts}",
            f"en_yavas_parca_tipleri: {slowest}",
            f"transport_turu: {summary.get('transport_turu', '')}",
            f"ai2_hazir: {bool((summary.get('ai2_hazirlik_durumu') or {}).get('ready'))}",
        ]
    )


def _recommended_max_tokens(case: dict, requested_max_tokens: int) -> int:
    kind = _piece_kind(case["metin"], case["adres"])
    if kind in {"numeric_row", "header_row", "technical_label_row", "very_short_note"}:
        return min(int(requested_max_tokens), 72)
    if kind in {"structured_short", "clipped_note"}:
        return min(int(requested_max_tokens), 80)
    return int(requested_max_tokens)


def main():
    parser = argparse.ArgumentParser(description="Run live anlamadim-v2 batch against Django + AI2")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Django API base URL")
    parser.add_argument("--auth-file", default=str(_repo_root() / "auth.json"))
    parser.add_argument("--transport", choices=["internal", "http"], default="internal")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--max-chars", type=int, default=140)
    parser.add_argument("--ai2-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--ai2-alias", default=DEFAULT_ALIAS)
    parser.add_argument("--ai2-model-path", default=str(DEFAULT_MODEL))
    parser.add_argument("--ai2-python", default=sys.executable)
    parser.add_argument("--ai2-ready-timeout", type=int, default=300)
    parser.add_argument("--ai2-poll-interval", type=int, default=5)
    parser.add_argument("--no-auto-start-ai2", action="store_true")
    parser.add_argument("--out", default=str(_repo_root() / "tools" / "anlamadim_live_batch_report.json"))
    args = parser.parse_args()

    auth = _load_auth(Path(args.auth_file))
    username = auth["username"]
    password = auth["password"]

    samples = _pick_samples(username, args.limit, args.max_chars)
    if not samples:
        raise RuntimeError("Canli batch icin ornek parca bulunamadi.")

    headers = {}
    if args.transport == "http":
        token = _get_token(args.base_url, username, password)
        headers = {"Authorization": f"Bearer {token}"}

    results = []
    problem_counter = Counter()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ai2_status = ensure_ai2_ready(
        base_url=args.ai2_base_url,
        python_exe=args.ai2_python,
        alias=args.ai2_alias,
        model_path=args.ai2_model_path,
        port=8002,
        ready_timeout_sec=args.ai2_ready_timeout,
        poll_interval_sec=args.ai2_poll_interval,
        auto_start=not args.no_auto_start_ai2,
    )

    def write_report():
        summary = _build_summary(results, problem_counter, args.transport, ai2_status)
        summary_text = _readable_summary(summary)

        payload = {
            "base_url": args.base_url,
            "transport": args.transport,
            "transport_note": _transport_note(args.transport),
            "dev_server_note": "HTTP transport ile Django dev-server tarafinda baglanti kararsizligi gorulebilir; final kalite olcumunde internal daha kararlı olabilir.",
            "username": username,
            "ai2_ready": bool(ai2_status.get("ready")),
            "ai2_status": ai2_status,
            "readable_summary": summary_text,
            "summary": summary,
            "results": results,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        out_path.with_suffix(".summary.txt").write_text(summary_text + "\n", encoding="utf-8")
        return summary

    summary = write_report()
    if not ai2_status.get("ready"):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"Rapor: {out_path}")
        raise SystemExit(
            f"AI2 hazir degil. transport={args.transport} detay={ai2_status.get('message') or 'bilinmiyor'}"
        )

    for case in samples:
        case_max_tokens = _recommended_max_tokens(case, args.max_tokens)
        payload = {
            "tema": "teknoloji",
            "tarz": "adim_adim",
            "seviye": "baslangic",
            "mesaj": "Burayi daha net ve parcaya bagli anlat.",
            "max_tokens": case_max_tokens,
        }
        started = time.perf_counter()
        try:
            if args.transport == "internal":
                response = _call_endpoint_internal(username, case["id"], payload)
            else:
                url = f"{args.base_url.rstrip('/')}/api/dokuman-asistani/parcalar/{case['id']}/anlamadim-v2/"
                response = _json_request(url, payload, headers=headers, timeout=args.request_timeout)
            evaluated = _evaluate_case(case, response)
        except urllib.error.HTTPError as exc:
            evaluated = {
                "parca_id": case["id"],
                "adres": case["adres"],
                "dokuman": case["dokuman"],
                "snippet": case["metin"][:180],
                "dokumanda_yok": False,
                "score": 0,
                "problems": [f"http_{exc.code}"],
                "error_message": f"{args.transport} transport HTTP {exc.code}",
                "response": {},
            }
        except TimeoutError:
            evaluated = {
                "parca_id": case["id"],
                "adres": case["adres"],
                "dokuman": case["dokuman"],
                "snippet": case["metin"][:180],
                "dokumanda_yok": False,
                "score": 0,
                "problems": ["timeout"],
                "error_message": f"{args.transport} transport timeout after {args.request_timeout}s",
                "response": {},
            }
        except Exception as exc:
            evaluated = {
                "parca_id": case["id"],
                "adres": case["adres"],
                "dokuman": case["dokuman"],
                "snippet": case["metin"][:180],
                "dokumanda_yok": False,
                "score": 0,
                "problems": [f"error:{type(exc).__name__}"],
                "error_message": f"{args.transport} transport error: {type(exc).__name__}: {exc}",
                "response": {},
            }
        evaluated["response_sec"] = round(time.perf_counter() - started, 2)
        evaluated["requested_max_tokens"] = case_max_tokens
        results.append(evaluated)
        problem_counter.update(evaluated["problems"])
        summary = write_report()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Rapor: {out_path}")


if __name__ == "__main__":
    main()
