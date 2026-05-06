"""Kod dosyalarini parser zorunlulugu olmadan anlamli segmentlere ayirmaya calisan helper'lar."""

import ast
import json
import re
from typing import Any


def _normalize_ws(text: str) -> str:
    """Kod segmentlerini karsilastirirken kullanilan tek satirlik normalize metni uret."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _segment(
    *,
    text: str,
    line_start: int,
    line_end: int,
    unit_kind: str,
    unit_name: str = "",
    parent_unit: str = "",
    chunk_kind: str = "",
    code_step_kind: str = "",
    is_test: bool = False,
    is_api_call: bool = False,
    is_assertion: bool = False,
    is_validation: bool = False,
    is_data_setup: bool = False,
    purpose_hints: list[str] | None = None,
) -> dict[str, Any]:
    """Tek bir kod parcasi icin ingestion ve explanation katmaninin bekledigi sozlugu uret."""
    return {
        "text": str(text or "").strip(),
        "line_start": max(1, int(line_start or 1)),
        "line_end": max(int(line_start or 1), int(line_end or line_start or 1)),
        "unit_kind": str(unit_kind or "block").strip() or "block",
        "unit_name": str(unit_name or "").strip(),
        "parent_unit": str(parent_unit or "").strip(),
        "chunk_kind": str(chunk_kind or "").strip() or (
            "code_comment" if unit_kind in {"comment", "docstring"} else "code_block"
        ),
        "code_step_kind": str(code_step_kind or "").strip(),
        "is_test": bool(is_test),
        "is_api_call": bool(is_api_call),
        "is_assertion": bool(is_assertion),
        "is_validation": bool(is_validation),
        "is_data_setup": bool(is_data_setup),
        "purpose_hints": [str(item).strip() for item in (purpose_hints or []) if str(item).strip()],
    }


def _dedupe_text_items(items: list[str]) -> list[str]:
    """Ayni amac ipucunun metada tekrar etmesini engeller."""
    out: list[str] = []
    seen = set()
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _slice_lines(lines: list[str], line_start: int, line_end: int) -> str:
    """Satir araligini koruyarak explanation ve ingestion icin ham blok metnini alir."""
    start = max(1, int(line_start or 1))
    end = max(start, int(line_end or start))
    return "\n".join(lines[start - 1:end]).strip()


def _comment_block_text(lines: list[str]) -> str:
    """Farkli yorum prefix'lerini temizleyip tek aciklama metnine indirger."""
    cleaned = []
    for line in lines:
        clean = re.sub(r"^\s*(#|//|/\*+|\*+/?|--|<!--|-->)\s*", "", line).strip()
        if clean:
            cleaned.append(clean)
    return " ".join(cleaned)


def _comment_line_match(line: str, language: str) -> bool:
    """Dil bazinda yorum satiri olarak davranan prefix'leri taniyarak segmentlemeye yardim eder."""
    stripped = str(line or "").strip()
    if not stripped:
        return False
    if language == "html":
        return stripped.startswith("<!--") or stripped.startswith("-->")
    if language == "sql":
        return stripped.startswith("--")
    if language in {"javascript", "typescript", "tsx", "jsx", "css"}:
        return stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("*/")
    return stripped.startswith("#")


def _iter_comment_segments(lines: list[str], language: str) -> list[dict[str, Any]]:
    """Ardisik yorum satirlarini tek code_comment segmenti halinde toplar."""
    segments: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _comment_line_match(line, language):
            i += 1
            continue
        start = i + 1
        buf = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if next_line.strip() and not _comment_line_match(next_line, language):
                break
            if next_line.strip():
                buf.append(next_line)
            i += 1
            if not next_line.strip():
                break
        segments.append(
            _segment(
                text=_comment_block_text(buf),
                line_start=start,
                line_end=start + len(buf) - 1,
                unit_kind="comment",
                chunk_kind="code_comment",
            )
        )
    return segments


def _line_indent(line: str) -> int:
    """Satirin sol bosluk miktarini dondurup block toplama helper'larina veri saglar."""
    return len(str(line or "")) - len(str(line or "").lstrip(" "))


def _collect_brace_block(lines: list[str], start_index: int, *, max_lines: int = 80) -> int:
    """Brace tabanli dillerde acilan blogun bitecegi satiri sezgisel olarak bulur."""
    balance = 0
    saw_open = False
    idx = start_index
    while idx < len(lines):
        current = lines[idx]
        balance += current.count("{") - current.count("}")
        if "{" in current:
            saw_open = True
        if idx > start_index and saw_open and balance <= 0:
            return idx + 1
        if idx > start_index and not current.strip() and not saw_open:
            return idx
        if idx - start_index + 1 >= max_lines:
            # Asiri uzun bloklarda segment boyutu kontrolden cikmasin.
            return idx + 1
        idx += 1
    return len(lines)


def _collect_indented_block(lines: list[str], start_index: int, *, max_lines: int = 80) -> int:
    """Python benzeri dillerde indent dusene kadar uzanan blogu toplar."""
    base = _line_indent(lines[start_index])
    idx = start_index + 1
    while idx < len(lines):
        current = lines[idx]
        stripped = current.strip()
        if not stripped:
            if idx - start_index >= 8:
                return idx
            idx += 1
            continue
        if _line_indent(current) <= base and not stripped.startswith((")", "]", "}")):
            return idx
        if idx - start_index + 1 >= max_lines:
            return idx + 1
        idx += 1
    return len(lines)


def _contains_api_call(text: str) -> bool:
    """Request/response veya network eylemi anlatan kod bloklarini sezgisel olarak isaretler."""
    return bool(
        re.search(
            r"\b(requests?|httpx|axios|fetch|urlopen|session|client|response)\b.*\b(get|post|put|patch|delete|request|send|json)\b"
            r"|\b(fetch|axios|urlopen)\s*\("
            r"|\b(Invoke-RestMethod|Invoke-WebRequest|curl)\b",
            str(text or ""),
            re.IGNORECASE,
        )
    )


def _contains_assertion(text: str, language: str) -> bool:
    """Test assertion'larini dillere gore ayirip explain/test-step sinyaline donusturur."""
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        return bool(re.search(r"\b(expect|assert)\b|to(Be|Equal|Contain|Have|Match)\b", str(text or ""), re.IGNORECASE))
    return bool(re.search(r"^\s*assert\b|\bassert[A-Z_]\w*\b|\bstatus_code\b", str(text or ""), re.IGNORECASE | re.MULTILINE))


def _contains_validation(text: str) -> bool:
    """Validation ve guardrail benzeri kontrolleri segment metasina tasir."""
    return bool(re.search(r"\b(validate|validator|dogrula|verify|check|status_code|schema|assert)\b", str(text or ""), re.IGNORECASE))


def _contains_data_setup(text: str) -> bool:
    """Fixture, payload veya mock kuran satirlari arrange asamasi icin tanir."""
    return bool(re.search(r"\b(setup|fixture|mock|stub|factory|prepare|hazirla|payload|data|token|headers?)\b", str(text or ""), re.IGNORECASE))


def _is_test_name(name: str, parent_unit: str = "") -> bool:
    """Fonksiyon ya da sinif adinin test yuzeyine ait olup olmadigini tahmin eder."""
    clean = str(name or "").strip()
    return clean.startswith("test_") or clean.endswith("_test") or str(parent_unit or "").startswith("Test")


def _extract_shell_name(line: str) -> str:
    """Shell fonksiyon tanimlarindan gorunen komut adini cikarmaya calisir."""
    patterns = [
        r"^\s*function\s+([A-Za-z_][\w.-]*)",
        r"^\s*([A-Za-z_][\w.-]*)\s*\(\)\s*\{",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(line or ""), re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _extract_shell_variable_name(line: str) -> str:
    """Shell atamasindaki degisken adini explanation metasina tasir."""
    match = re.search(r"^\s*(?:export\s+)?[$]?([A-Za-z_][\w:.-]*)\s*=", str(line or ""))
    return (match.group(1) if match else "").strip()


def _extract_command_name(line: str, language: str) -> str:
    """Shell/Powershell satirinda one cikan komut ya da API aracini ayiklar."""
    stripped = str(line or "").strip()
    if not stripped:
        return ""
    if language in {"shell", "powershell", "batch"}:
        for pattern in (
            r"=\s*(Invoke-RestMethod|Invoke-WebRequest|curl|wget|Invoke-Expression|Start-Process)\b",
            r"^\s*&?\s*(Invoke-RestMethod|Invoke-WebRequest|curl|wget|jq|python|python3|node|npm|git|docker|kubectl|pwsh|bash|sh)\b",
            r"\|\s*([A-Za-z_][\w.-]*)\b",
        ):
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                return match.group(1)
        if _contains_api_call(stripped):
            for pattern in (r"\b(Invoke-RestMethod|Invoke-WebRequest|curl|wget)\b", r"\b([A-Za-z_][\w.-]*)\b"):
                match = re.search(pattern, stripped, re.IGNORECASE)
                if match:
                    return match.group(1)
        match = re.search(r"\b([A-Za-z_][\w.-]*)\b", stripped)
        return (match.group(1) if match else "").strip()
    return ""


def _extract_js_name(line: str) -> str:
    """JS/TS tanim satirlarindan fonksiyon, class veya degisken adini bulur."""
    patterns = [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"^\s*(?:async\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*\{",
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>",
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(line or ""))
        if match:
            return match.group(1)
    return ""


def _extract_js_callback_name(line: str) -> str:
    stripped = str(line or "").strip()
    if "=>" not in stripped:
        return ""
    event_match = re.search(r"\.addEventListener\(\s*['\"]([^'\"]+)['\"]", stripped, re.IGNORECASE)
    if event_match:
        event_name = re.sub(r"[^A-Za-z0-9_]+", "_", event_match.group(1).strip()).strip("_")
        return f"{event_name or 'event'}_handler"
    for pattern in (
        r"\.(then|catch|finally)\s*\(",
        r"\.(map|filter|forEach|reduce|find)\s*\(",
        r"\b(useEffect|setTimeout|setInterval)\s*\(",
    ):
        match = re.search(pattern, stripped, re.IGNORECASE)
        if match:
            name = re.sub(r"[^A-Za-z0-9_]+", "_", match.group(1).strip()).strip("_")
            return f"{name or 'callback'}_callback"
    return "callback"


def _extract_js_api_name(line: str) -> str:
    stripped = str(line or "").strip()
    for pattern in (
        r"\b(fetch)\s*\(",
        r"\baxios\.(get|post|put|patch|delete|request)\s*\(",
        r"\b[A-Za-z_$][A-Za-z0-9_$]*\.(get|post|put|patch|delete)\s*\(",
    ):
        match = re.search(pattern, stripped, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _extract_js_test_name(line: str) -> str:
    """Jest veya benzeri test satirlarindaki insan okunur adi segment ismine cevirir."""
    match = re.search(r"^\s*(describe|it|test)\s*\(\s*['\"]([^'\"]+)['\"]", str(line or ""))
    if match:
        return re.sub(r"\s+", "_", match.group(2).strip())
    return ""


def _extract_markup_name(line: str) -> str:
    """Markup satirindaki ilk HTML/XML etiket adini cikarir."""
    match = re.search(r"<([a-z0-9_-]+)\b", str(line or ""), re.IGNORECASE)
    return (match.group(1).lower() if match else "").strip()


def _extract_css_selector(line: str) -> str:
    """CSS kural satirindan seciciyi ayiklayip segment basligina tasir."""
    stripped = str(line or "").strip()
    if not stripped:
        return ""
    if stripped.startswith("@"):
        return stripped.split("{", 1)[0].strip()
    match = re.match(r"([^{]+)\{", stripped)
    return match.group(1).strip() if match else ""


def _extract_config_key(line: str, language: str) -> str:
    """JSON/YAML benzeri config satirlarinda anahtar adini cikarir."""
    stripped = str(line or "").strip().lstrip("-").strip()
    if language == "json":
        match = re.match(r'"([^"]+)"\s*:', stripped)
        return match.group(1).strip() if match else ""
    if stripped.startswith("<<:"):
        return "<<"
    quoted_match = re.match(r'["\']([^"\']+)["\']\s*:', stripped)
    if quoted_match:
        return quoted_match.group(1).strip()
    match = re.match(r"([A-Za-z0-9_.-]+)\s*:", stripped)
    return match.group(1).strip() if match else ""


def _extract_sql_table_name(text: str) -> str:
    patterns = [
        r"\bfrom\s+([A-Za-z_][A-Za-z0-9_.$]*)",
        r"\bjoin\s+([A-Za-z_][A-Za-z0-9_.$]*)",
        r"\binto\s+([A-Za-z_][A-Za-z0-9_.$]*)",
        r"\bupdate\s+([A-Za-z_][A-Za-z0-9_.$]*)",
    ]
    source = str(text or "")
    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _extract_sql_segment_name(text: str, kind: str) -> str:
    source = str(text or "").strip()
    table = _extract_sql_table_name(source)
    label = str(kind or "").replace("sql_", "").strip() or "statement"
    if label in {"from_join", "where_group", "where", "group_by", "order_by", "set"}:
        label = label
    if table:
        return f"{label}_{table}".strip("_")
    return f"{label}_clause" if label in {"select", "with", "from_join", "where_group", "where", "group_by", "order_by", "set"} else label


_SQL_INLINE_CLAUSE_PATTERNS: list[tuple[str, str]] = [
    ("group by", "sql_where_group"),
    ("order by", "sql_where_group"),
    ("left join", "sql_from_join"),
    ("right join", "sql_from_join"),
    ("inner join", "sql_from_join"),
    ("outer join", "sql_from_join"),
    ("cross join", "sql_from_join"),
    ("where", "sql_where_group"),
    ("having", "sql_where_group"),
    ("limit", "sql_where_group"),
    ("from", "sql_from_join"),
    ("join", "sql_from_join"),
    ("select", "sql_select"),
    ("with", "sql_with"),
    ("insert", "sql_insert"),
    ("update", "sql_update"),
    ("delete", "sql_delete"),
    ("create", "sql_create"),
    ("alter", "sql_alter"),
    ("set", "sql_set"),
]


def _sql_boundary_char(char: str) -> bool:
    return not char or not (char.isalnum() or char in {"_", "$", "."})


def _sql_line_clause_slices(line: str) -> list[tuple[str, str]]:
    """Tek SQL satirinda gorunen clause baslangiclarini depth-aware sekilde ayir."""
    source = str(line or "")
    if not source.strip():
        return []
    hits: list[tuple[int, str]] = []
    quote = ""
    depth = 0
    idx = 0
    while idx < len(source):
        char = source[idx]
        if quote:
            if char == quote and (idx == 0 or source[idx - 1] != "\\"):
                quote = ""
            idx += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            idx += 1
            continue
        if char == "(":
            depth += 1
            idx += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            idx += 1
            continue
        if depth == 0:
            lowered_tail = source[idx:].lower()
            matched = False
            for phrase, kind in _SQL_INLINE_CLAUSE_PATTERNS:
                if not lowered_tail.startswith(phrase):
                    continue
                prev_char = source[idx - 1] if idx > 0 else ""
                next_pos = idx + len(phrase)
                next_char = source[next_pos] if next_pos < len(source) else ""
                if not (_sql_boundary_char(prev_char) and _sql_boundary_char(next_char)):
                    continue
                if not hits or hits[-1][1] != kind:
                    hits.append((idx, kind))
                idx += len(phrase)
                matched = True
                break
            if matched:
                continue
        idx += 1

    slices: list[tuple[str, str]] = []
    for hit_index, (start, kind) in enumerate(hits):
        end = hits[hit_index + 1][0] if hit_index + 1 < len(hits) else len(source)
        clause_text = source[start:end].strip()
        if clause_text:
            slices.append((kind, clause_text))
    return slices


def _sql_clause_groups(statement_text: str, *, statement_start_line: int) -> list[tuple[str, list[tuple[int, str]]]]:
    """SQL statement icinde gorunen clause bloklarini satir ici ayrimlarla grupla."""
    groups: list[tuple[str, list[tuple[int, str]]]] = []
    for rel_index, raw_line in enumerate(str(statement_text or "").splitlines()):
        line_no = statement_start_line + rel_index
        stripped = raw_line.strip()
        if not stripped or _comment_line_match(raw_line, "sql"):
            continue
        slices = _sql_line_clause_slices(raw_line)
        if not slices:
            if groups and stripped not in {")", ");", "(", ","}:
                groups[-1][1].append((line_no, stripped))
            continue
        for slice_index, (kind, clause_text) in enumerate(slices):
            if (
                groups
                and groups[-1][0] == kind
                and slice_index == 0
                and groups[-1][1]
                and groups[-1][1][-1][0] == line_no - 1
            ):
                groups[-1][1].append((line_no, clause_text))
            else:
                groups.append((kind, [(line_no, clause_text)]))
    return groups


def _config_value_hints(name: str, value_text: str) -> list[str]:
    key = str(name or "").lower()
    value = str(value_text or "").lower()
    hints: list[str] = ["config"]
    if any(token in key for token in {"url", "host", "base", "endpoint", "api", "origin", "uri", "port"}):
        hints.append("network")
        hints.append("connection")
    if any(token in key for token in {"token", "secret", "key", "password", "auth", "cert", "ssl", "tls", "cors"}):
        hints.append("security")
    if any(token in key for token in {"service", "server", "worker", "client", "logging", "queue", "broker"}):
        hints.append("service")
    if any(token in key for token in {"retry", "timeout", "interval", "delay", "period", "backoff"}):
        hints.append("runtime")
    if any(token in key for token in {"threshold", "limit", "max", "min", "count", "size", "ttl"}):
        hints.append("threshold")
    if any(token in key for token in {"enabled", "disabled", "feature", "flag"}):
        hints.append("toggle")
    if any(token in key for token in {"env", "environment", "profile", "override", "stage"}):
        hints.append("environment_override")
    if any(token in key for token in {"theme", "color", "layout", "style"}):
        hints.append("ui")
    if any(token in key for token in {"path", "dir", "file", "folder"}):
        hints.append("path")
    if any(token in value for token in {"&", "*", "|", ">"}):
        hints.append("structured_value")
    if value in {"true", "false"}:
        hints.append("boolean")
    if "${" in value or "%" in value:
        hints.append("environment_override")
    return _dedupe_text_items(hints)


def _purpose_hints(language: str, kind: str, text: str, *, name: str = "") -> list[str]:
    lowered = str(text or "").lower()
    hints: list[str] = []
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        hints.append("javascript")
    elif language in {"shell", "powershell", "batch"}:
        hints.append("shell")
    elif language in {"json", "yaml"}:
        hints.append("config")
    elif language == "sql":
        hints.append("sql")
    elif language in {"html", "css"}:
        hints.append("frontend")

    if kind in {"test_function", "assertion"}:
        hints.append("test")
    if kind == "api_call":
        hints.append("api_call")
    if kind in {"control_flow", "sql_where_group"}:
        hints.append("control_flow")
    if kind == "method":
        hints.append("stateful_behavior")
    if kind in {"variable", "constant", "config_entry"}:
        hints.append("data_setup")
    if kind in {"markup_block", "script_block", "style_block", "style_rule"}:
        hints.append("ui")
    if kind == "markup_block":
        hints.append("structure")
    if kind in {"style_block", "style_rule"}:
        hints.append("presentation")
    if kind == "script_block":
        hints.append("behavior")
    if kind == "command":
        hints.append("command")
    if kind == "api_call":
        hints.append("external_call")
    if kind.startswith("sql_"):
        if kind in {"sql_insert", "sql_update", "sql_delete", "sql_create", "sql_alter"}:
            hints.append("write_query")
        else:
            hints.append("read_query")
    if kind in {"sql_where", "sql_where_group"}:
        hints.append("filter")
    if kind == "sql_group_by":
        hints.append("aggregation")
    if kind == "sql_order_by":
        hints.append("sorting")
    if kind == "sql_set":
        hints.append("assignment")
    if kind == "section":
        hints.append("group")
    if language in {"json", "yaml"}:
        hints.extend(_config_value_hints(name, text))
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        if re.search(r"\b(addeventlistener|preventdefault|stoppropagation)\b", lowered):
            hints.append("event_handler")
        if re.search(r"\.(then|catch|finally)\s*\(", str(text or ""), re.IGNORECASE):
            hints.append("promise_chain")
        if re.search(r"\bset[A-Z][A-Za-z0-9_]*\(|\bdispatch\(|\buseState\b", str(text or "")):
            hints.append("state_update")
        if re.search(r"\b(this|props|state)\.", str(text or "")):
            hints.append("component_context")
        if re.search(r"\b(?:this|[A-Za-z_$][A-Za-z0-9_$]*)\.[A-Za-z_$][A-Za-z0-9_$]*\s*=", str(text or "")):
            hints.append("property_assignment")
        if re.search(r"\breturn\s*<|\brender[A-Za-z_]*\(", str(text or "")):
            hints.append("ui_result")
        if re.search(r"\breturn\s*<", str(text or "")) or re.match(r"^[A-Z][A-Za-z0-9_]*$", str(name or "")):
            hints.append("component_like")
        if "=>" in str(text or ""):
            hints.append("callback")
    if language in {"shell", "powershell", "batch"}:
        if "|" in str(text or ""):
            hints.append("pipeline")
        if re.search(r"^\s*\$env:", str(text or ""), re.IGNORECASE):
            hints.append("environment_variable")
        if re.search(r"\bStart-Process\b", str(text or ""), re.IGNORECASE):
            hints.append("process_launch")
    if _contains_api_call(text) and kind not in {"markup_block", "style_block", "style_rule", "section"}:
        hints.append("api_call")
    if _contains_assertion(text, language):
        hints.append("assertion")
    if _contains_validation(text):
        hints.append("validation")
    return _dedupe_text_items(hints)


def _python_docstring_expr(node: Any):
    body = list(getattr(node, "body", []) or [])
    if not body:
        return None
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
        return first
    return None


def _python_target_name(node: Any) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _python_assign_name(node: Any) -> str:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            name = _python_target_name(target)
            if name:
                return name
    if isinstance(node, ast.AnnAssign):
        return _python_target_name(node.target)
    if isinstance(node, ast.AugAssign):
        return _python_target_name(node.target)
    return ""


def _python_statement_lists(node: Any) -> list[list[Any]]:
    lists = []
    for attr in ("body", "orelse", "finalbody"):
        value = getattr(node, attr, None)
        if isinstance(value, list) and value:
            lists.append(value)
    for handler in getattr(node, "handlers", []) or []:
        if getattr(handler, "body", None):
            lists.append(list(handler.body))
    for case in getattr(node, "cases", []) or []:
        if getattr(case, "body", None):
            lists.append(list(case.body))
    return lists


def _python_statement_segments(statements: list[Any], lines: list[str], *, parent_unit: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for stmt in statements:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(stmt, "lineno", 1)
        end = getattr(stmt, "end_lineno", start)
        stmt_text = _slice_lines(lines, start, end)
        if isinstance(stmt, ast.Assert):
            segments.append(_segment(text=stmt_text, line_start=start, line_end=end, unit_kind="assertion", unit_name=f"assert_{start}", parent_unit=parent_unit, is_assertion=True, is_validation=True))
        elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)):
            segments.append(_segment(text=stmt_text, line_start=start, line_end=end, unit_kind="control_flow", unit_name=type(stmt).__name__.lower(), parent_unit=parent_unit, is_validation=_contains_validation(stmt_text)))
        elif _contains_api_call(stmt_text):
            segments.append(_segment(text=stmt_text, line_start=start, line_end=end, unit_kind="api_call", unit_name=_python_assign_name(stmt) or f"api_{start}", parent_unit=parent_unit, is_api_call=True))
        elif _contains_assertion(stmt_text, "python"):
            segments.append(_segment(text=stmt_text, line_start=start, line_end=end, unit_kind="assertion", unit_name=f"assert_{start}", parent_unit=parent_unit, is_assertion=True, is_validation=True))
        for nested in _python_statement_lists(stmt):
            segments.extend(_python_statement_segments(nested, lines, parent_unit=parent_unit))
    return segments


def _python_test_step_kind(stmt: Any, stmt_text: str) -> str:
    """Python test statement'ini arrange/act/assert akisinin uygun asamasina yerlestirir."""
    if isinstance(stmt, ast.Assert) or _contains_assertion(stmt_text, "python"):
        return "assert"
    if _contains_api_call(stmt_text):
        return "act"
    if isinstance(stmt, (ast.Expr, ast.Return)) and re.search(r"\b(call|run|execute|invoke|create|post|get|put|patch|delete)\b", stmt_text, re.IGNORECASE):
        return "act"
    if _contains_data_setup(stmt_text):
        return "arrange"
    return "arrange"


def _python_test_step_segments(node: Any, lines: list[str], *, unit_name: str) -> list[dict[str, Any]]:
    """Ayni asamaya ait test statement'lerini tek segmentte gruplayarak okunabilirlik kazandirir."""
    body = list(getattr(node, "body", []) or [])
    if _python_docstring_expr(node) is not None and body:
        body = body[1:]
    groups: list[tuple[str, list[Any]]] = []
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stmt_text = _slice_lines(lines, getattr(stmt, "lineno", 1), getattr(stmt, "end_lineno", getattr(stmt, "lineno", 1)))
        stage = _python_test_step_kind(stmt, stmt_text)
        # Aynı faza ait komşu statement'leri tek chunk yapmak explain katmaninda arrange/act/asserti belirginlestirir.
        if groups and groups[-1][0] == stage:
            groups[-1][1].append(stmt)
        else:
            groups.append((stage, [stmt]))
    out = []
    for index, (stage, stmt_group) in enumerate(groups, start=1):
        start = getattr(stmt_group[0], "lineno", 1)
        end = getattr(stmt_group[-1], "end_lineno", getattr(stmt_group[-1], "lineno", 1))
        text = _slice_lines(lines, start, end)
        out.append(
            _segment(
                text=text,
                line_start=start,
                line_end=end,
                unit_kind="test_step",
                unit_name=f"{unit_name}:{stage}:{index}",
                parent_unit=unit_name,
                code_step_kind=stage,
                is_test=True,
                is_api_call=stage == "act" and _contains_api_call(text),
                is_assertion=stage == "assert",
                is_validation=stage == "assert",
                is_data_setup=stage == "arrange",
            )
        )
    return out


def _python_import_segments(module: ast.Module, lines: list[str]) -> list[dict[str, Any]]:
    """Ardisik import bloklarini tek segmentte toplayip ust yuzey baglamini korur."""
    out = []
    index = 0
    while index < len(module.body):
        node = module.body[index]
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            index += 1
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        names = []
        while index < len(module.body) and isinstance(module.body[index], (ast.Import, ast.ImportFrom)):
            current = module.body[index]
            start = min(start, current.lineno)
            end = max(end, getattr(current, "end_lineno", current.lineno))
            if isinstance(current, ast.Import):
                names.extend(alias.name for alias in current.names)
            else:
                prefix = f"{current.module or ''}:".strip(":")
                names.extend(f"{prefix}.{alias.name}".strip(".") for alias in current.names)
            index += 1
        out.append(_segment(text=_slice_lines(lines, start, end), line_start=start, line_end=end, unit_kind="import", unit_name=", ".join(names[:3])))
    return out


def _python_segments(text: str) -> list[dict[str, Any]]:
    """Python dosyasini docstring, unit, statement ve test-step segmentlerine ayirir."""
    lines = str(text or "").splitlines()
    segments = _iter_comment_segments(lines, "python")
    try:
        module = ast.parse(text)
    except SyntaxError:
        return segments

    segments.extend(_python_import_segments(module, lines))
    module_doc = _python_docstring_expr(module)
    if module_doc is not None:
        segments.append(_segment(text=_slice_lines(lines, module_doc.lineno, getattr(module_doc, "end_lineno", module_doc.lineno)), line_start=module_doc.lineno, line_end=getattr(module_doc, "end_lineno", module_doc.lineno), unit_kind="docstring", unit_name="module_docstring", chunk_kind="code_comment"))

    for node in module.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            name = _python_assign_name(node)
            kind = "constant" if name.isupper() and name else "variable"
            segments.append(_segment(text=_slice_lines(lines, node.lineno, getattr(node, "end_lineno", node.lineno)), line_start=node.lineno, line_end=getattr(node, "end_lineno", node.lineno), unit_kind=kind, unit_name=name, is_data_setup=kind == "variable"))
            continue
        if isinstance(node, ast.ClassDef):
            segments.append(_segment(text=_slice_lines(lines, node.lineno, getattr(node, "end_lineno", node.lineno)), line_start=node.lineno, line_end=getattr(node, "end_lineno", node.lineno), unit_kind="class", unit_name=node.name))
            class_doc = _python_docstring_expr(node)
            if class_doc is not None:
                segments.append(_segment(text=_slice_lines(lines, class_doc.lineno, getattr(class_doc, "end_lineno", class_doc.lineno)), line_start=class_doc.lineno, line_end=getattr(class_doc, "end_lineno", class_doc.lineno), unit_kind="docstring", unit_name=f"{node.name}.docstring", parent_unit=node.name, chunk_kind="code_comment"))
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                method_kind = "test_function" if _is_test_name(child.name, node.name) else "method"
                segments.append(_segment(text=_slice_lines(lines, child.lineno, getattr(child, "end_lineno", child.lineno)), line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno), unit_kind=method_kind, unit_name=child.name, parent_unit=node.name, is_test=method_kind == "test_function"))
                method_doc = _python_docstring_expr(child)
                body = list(child.body)[1:] if method_doc is not None else list(child.body)
                if method_doc is not None:
                    segments.append(_segment(text=_slice_lines(lines, method_doc.lineno, getattr(method_doc, "end_lineno", method_doc.lineno)), line_start=method_doc.lineno, line_end=getattr(method_doc, "end_lineno", method_doc.lineno), unit_kind="docstring", unit_name=f"{child.name}.docstring", parent_unit=child.name, chunk_kind="code_comment"))
                segments.extend(_python_statement_segments(body, lines, parent_unit=child.name))
                if method_kind == "test_function":
                    segments.extend(_python_test_step_segments(child, lines, unit_name=child.name))
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_kind = "test_function" if _is_test_name(node.name) else "function"
            segments.append(_segment(text=_slice_lines(lines, node.lineno, getattr(node, "end_lineno", node.lineno)), line_start=node.lineno, line_end=getattr(node, "end_lineno", node.lineno), unit_kind=function_kind, unit_name=node.name, is_test=function_kind == "test_function"))
            function_doc = _python_docstring_expr(node)
            body = list(node.body)[1:] if function_doc is not None else list(node.body)
            if function_doc is not None:
                segments.append(_segment(text=_slice_lines(lines, function_doc.lineno, getattr(function_doc, "end_lineno", function_doc.lineno)), line_start=function_doc.lineno, line_end=getattr(function_doc, "end_lineno", function_doc.lineno), unit_kind="docstring", unit_name=f"{node.name}.docstring", parent_unit=node.name, chunk_kind="code_comment"))
            segments.extend(_python_statement_segments(body, lines, parent_unit=node.name))
            if function_kind == "test_function":
                segments.extend(_python_test_step_segments(node, lines, unit_name=node.name))
    return segments


def _block_symbol(line: str) -> str:
    patterns = [
        r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*function\s+([A-Za-z_][A-Za-z0-9_-]*)",
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"^\s*(?:async\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*\{",
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>",
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(1)
    return ""


def _generic_kind(line: str, language: str) -> str:
    """Python disi dillerde satiri kaba ama faydali birim turlerine ayir."""
    stripped = str(line or "").strip()
    lowered = stripped.lower()
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        if re.search(r"^\s*(import\b|export\s+.*from\b|const\s+\w+\s*=\s*require\()", line):
            return "import"
        if re.search(r"^\s*(describe|it|test)\s*\(", line):
            return "test_function"
        if re.search(r"^\s*(export\s+)?class\b", line):
            return "class"
        if re.search(r"^\s*(?:export\s+)?(?:async\s+)?function\b", line):
            return "function"
        if re.search(r"^\s*(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>", line):
            return "function"
        if "=>" in line and ("{" in line or stripped.endswith("=>")):
            return "function"
        if re.search(r"^\s*(?:async\s+)?[A-Za-z_$][A-Za-z0-9_$]*\s*\([^)]*\)\s*\{", line) and not re.search(r"^\s*(if|for|while|switch|catch)\b", line):
            return "function"
        if re.search(r"^\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\([^)]*\)\s*\{", line) and not re.search(r"^\s*(if|for|while|switch|catch)\b", line):
            return "function"
        if re.search(r"\b(expect|assert|should)\b", line, re.IGNORECASE):
            return "assertion"
        if _contains_api_call(line):
            return "api_call"
        if re.search(r"^\s*(if|for|while|switch|try|catch|else\s+if)\b", line):
            return "control_flow"
        if re.search(r"^\s*(const|let|var)\b", line):
            return "constant" if re.search(r"^\s*const\b", line) else "variable"
        return "block"
    if language == "html":
        if stripped.startswith("</"):
            return "block"
        if re.search(r"<script\b", lowered):
            return "script_block"
        if re.search(r"<style\b", lowered):
            return "style_block"
        if _contains_api_call(line):
            return "api_call"
        return "markup_block"
    if language == "css":
        if re.search(r"^\s*@", line):
            return "style_block"
        return "style_rule"
    if language in {"json", "yaml"}:
        return "config_entry"
    if language == "sql":
        if re.search(r"^\s*(from|join|left join|right join|inner join|outer join|cross join)\b", lowered):
            return "sql_from_join"
        if re.search(r"^\s*(where|having|limit)\b", lowered):
            return "sql_where"
        if re.search(r"^\s*group by\b", lowered):
            return "sql_group_by"
        if re.search(r"^\s*order by\b", lowered):
            return "sql_order_by"
        if re.search(r"^\s*set\b", lowered):
            return "sql_set"
        if re.search(r"^\s*over\s*\(", lowered):
            return "sql_where_group"
        keyword = lowered.split(" ", 1)[0]
        if keyword in {"select", "insert", "update", "delete", "create", "alter", "with"}:
            return f"sql_{keyword}"
        return "sql_statement"
    if language in {"shell", "powershell", "batch"}:
        if re.search(r"^\s*function\b", line, re.IGNORECASE) or re.search(r"^\s*[A-Za-z_][\w.-]*\s*\(\)\s*\{", line):
            return "function"
        if re.search(r"^\s*(if|for|foreach|while|case|switch|try)\b", line, re.IGNORECASE):
            return "control_flow"
        if re.search(r"\b(assert|test-path|should\s+-be|throw)\b", line, re.IGNORECASE):
            return "assertion"
        if _contains_api_call(line):
            return "api_call"
        if re.search(r"^\s*(export\s+)?[$]?[A-Za-z_][\w:.-]*\s*=", line):
            return "variable"
        return "command"
    return "block"


def _generic_block_name(line: str, kind: str, language: str) -> str:
    if language in {"javascript", "typescript", "tsx", "jsx"}:
        if kind == "api_call":
            return _extract_js_api_name(line) or _extract_js_name(line) or _extract_js_callback_name(line)
        if kind == "test_function":
            return _extract_js_test_name(line) or _extract_js_name(line)
        return _extract_js_name(line) or _extract_js_callback_name(line)
    if language in {"shell", "powershell", "batch"}:
        if kind == "variable":
            return _extract_shell_variable_name(line)
        if kind == "api_call":
            return _extract_command_name(line, language)
        if kind == "command":
            return _extract_command_name(line, language)
        return _extract_shell_name(line)
    if language == "html":
        return _extract_markup_name(line)
    if language == "css":
        return _extract_css_selector(line)
    if language in {"json", "yaml"}:
        return _extract_config_key(line, language)
    if language == "sql":
        return _extract_sql_segment_name(line, kind)
    if kind in {"sql_from_join", "sql_where_group", "sql_where", "sql_group_by", "sql_order_by", "sql_set"}:
        return kind.replace("sql_", "")
    return ""


def _generic_inner_segments(
    block_text: str,
    *,
    language: str,
    parent_unit: str,
    start_line: int,
    is_test: bool,
) -> list[dict[str, Any]]:
    if not parent_unit:
        return []

    block_lines = str(block_text or "").splitlines()
    if len(block_lines) <= 1:
        return []

    allowed = {"class", "function", "method", "test_function", "api_call", "assertion", "control_flow", "variable", "constant", "command", "style_block", "script_block", "markup_block", "style_rule"}
    container_kinds = {"class", "function", "method", "test_function", "control_flow", "style_block", "script_block", "markup_block"}
    stack = [{"indent": _line_indent(block_lines[0]), "name": parent_unit, "kind": "root"}]
    segments: list[dict[str, Any]] = []

    for rel_index, inner_line in enumerate(block_lines[1:], start=1):
        stripped = str(inner_line or "").strip()
        if not stripped or _comment_line_match(inner_line, language):
            continue
        indent = _line_indent(inner_line)
        if stripped.startswith(("}", "});", "});", "</")):
            while len(stack) > 1 and indent <= stack[-1]["indent"]:
                stack.pop()
            continue
        while len(stack) > 1 and indent <= stack[-1]["indent"]:
            stack.pop()

        current_parent = stack[-1]["name"] or parent_unit
        current_parent_kind = stack[-1].get("kind") or ""
        nested_language = language
        if language == "html" and current_parent == "style":
            nested_language = "css"
        elif language == "html" and current_parent == "script":
            nested_language = "javascript"

        inner_kind = _generic_kind(inner_line, nested_language)
        if nested_language in {"javascript", "typescript", "tsx", "jsx"} and inner_kind == "function" and current_parent_kind == "class":
            inner_kind = "method"
        if inner_kind not in allowed:
            continue
        inner_text = stripped
        inner_name = (
            _generic_block_name(inner_line, inner_kind, nested_language)
            if inner_kind == "api_call"
            else (_block_symbol(inner_line) or _generic_block_name(inner_line, inner_kind, nested_language))
        )
        segments.append(
            _segment(
                text=inner_text,
                line_start=start_line + rel_index,
                line_end=start_line + rel_index,
                unit_kind=inner_kind,
                unit_name=inner_name,
                parent_unit=current_parent,
                is_test=is_test or inner_kind == "test_function",
                is_api_call=inner_kind == "api_call" or _contains_api_call(inner_text),
                is_assertion=inner_kind == "assertion" or _contains_assertion(inner_text, nested_language),
                is_validation=inner_kind == "assertion" or _contains_validation(inner_text),
                is_data_setup=inner_kind in {"variable", "constant"},
                purpose_hints=_purpose_hints(nested_language, inner_kind, inner_text, name=inner_name),
            )
        )
        # Ic ice yapilarda bir sonraki alt satirlarin dogru ebeveyne baglanmasini sagla.
        if inner_kind in container_kinds and inner_name:
            stack.append({"indent": indent, "name": inner_name, "kind": inner_kind})

    return segments


def _generic_segments(text: str, language: str) -> list[dict[str, Any]]:
    """Brace, indent ve satir ipuclarini kullanarak parser benzeri olmayan segmentler uret."""
    lines = str(text or "").splitlines()
    segments = _iter_comment_segments(lines, language)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or _comment_line_match(line, language):
            i += 1
            continue
        kind = _generic_kind(line, language)
        if language == "html" and stripped.startswith("</"):
            i += 1
            continue
        start = i
        end = i + 1
        if kind == "import":
            while end < len(lines) and lines[end].strip() and _generic_kind(lines[end], language) == "import":
                end += 1
        elif language in {"javascript", "typescript", "tsx", "jsx", "css"} and ("{" in line or kind in {"function", "class", "test_function", "style_rule", "control_flow"}):
            end = _collect_brace_block(lines, start)
        elif language == "html":
            tag = re.search(r"<([a-z0-9_-]+)\b", stripped, re.IGNORECASE)
            tag_name = tag.group(1).lower() if tag else ""
            while end < len(lines) and tag_name:
                if re.search(fr"</{re.escape(tag_name)}\s*>", lines[end], re.IGNORECASE):
                    end += 1
                    break
                if end - start >= 40:
                    break
                end += 1
        elif language == "sql":
            while end < len(lines):
                if ";" in lines[end - 1]:
                    break
                if end >= len(lines):
                    break
                if not lines[end].strip() and end - start >= 4:
                    break
                end += 1
                if end - start >= 30:
                    break
        elif language in {"shell", "powershell", "batch"} and kind in {"function", "control_flow"}:
            end = _collect_brace_block(lines, start) if "{" in line else _collect_indented_block(lines, start)
        else:
            while end < len(lines):
                next_line = lines[end]
                if not next_line.strip():
                    if end - start >= 6:
                        break
                    end += 1
                    continue
                if _comment_line_match(next_line, language):
                    break
                if _generic_kind(next_line, language) != "block" and end > start:
                    break
                end += 1
                if end - start >= 12:
                    break
        block_text = _slice_lines(lines, start + 1, end)
        if _normalize_ws(block_text):
            name = _generic_block_name(line, kind, language) if kind == "api_call" else (_block_symbol(line) or _generic_block_name(line, kind, language))
            parent_unit = name if kind in {"function", "method", "test_function", "class", "style_block", "script_block"} else ""
            if language == "html" and kind == "markup_block":
                parent_unit = name or "markup"
            segments.append(
                _segment(
                    text=block_text,
                    line_start=start + 1,
                    line_end=end,
                    unit_kind=kind,
                    unit_name=name,
                    parent_unit="",
                    is_test=kind == "test_function",
                    is_api_call=kind == "api_call" or _contains_api_call(block_text),
                    is_assertion=kind == "assertion" or _contains_assertion(block_text, language),
                    is_validation=_contains_validation(block_text),
                    is_data_setup=kind in {"variable", "constant", "config_entry", "section"},
                    purpose_hints=_purpose_hints(language, kind, block_text, name=name),
                )
            )
            segments.extend(
                _generic_inner_segments(
                    block_text,
                    language=language,
                    parent_unit=parent_unit,
                    start_line=start + 1,
                    is_test=kind == "test_function",
                )
            )
        i = max(end, i + 1)
    return segments


def _config_segments(text: str, language: str) -> list[dict[str, Any]]:
    """JSON/YAML benzeri config dosyalarinda section ve key/value bloklarini ayir."""
    lines = str(text or "").splitlines()
    segments = _iter_comment_segments(lines, language)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or _comment_line_match(line, language):
            i += 1
            continue
        name = _extract_config_key(line, language)
        if not name:
            i += 1
            continue
        base_indent = _line_indent(line)
        is_section = False
        value_text = stripped
        if language == "json":
            is_section = bool(re.search(r":\s*[\[{]\s*,?$", stripped))
        else:
            value_part = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            is_section = not value_part or value_part in {"|", ">"} or value_part.startswith("&")
        end = i + 1
        while end < len(lines):
            next_line = lines[end]
            if not next_line.strip():
                end += 1
                continue
            if _line_indent(next_line) <= base_indent and end > i:
                break
            end += 1
            if end - i >= 40:
                break
        if end <= i + 1:
            end = i + 1
        block_text = _slice_lines(lines, i + 1, end)
        kind = "section" if is_section and end > i + 1 else "config_entry"
        segments.append(
            _segment(
                text=block_text,
                line_start=i + 1,
                line_end=end,
                unit_kind=kind,
                unit_name=name,
                is_data_setup=True,
                purpose_hints=_purpose_hints(language, kind, value_text, name=name),
            )
        )
        if kind == "section":
            # Section altindaki dogrudan anahtarlari da ayri config entry olarak gorunur kil.
            for child_offset, child_line in enumerate(lines[i + 1:end], start=i + 2):
                child_stripped = child_line.strip()
                if not child_stripped or _line_indent(child_line) <= base_indent:
                    continue
                child_name = _extract_config_key(child_line, language)
                if not child_name:
                    continue
                if language == "json":
                    child_is_section = bool(re.search(r":\s*[\[{]\s*,?$", child_stripped))
                else:
                    child_value = child_stripped.split(":", 1)[1].strip() if ":" in child_stripped else ""
                    child_is_section = not child_value or child_value in {"|", ">"} or child_value.startswith("&")
                child_kind = "section" if child_is_section else "config_entry"
                segments.append(
                    _segment(
                        text=child_stripped.rstrip(","),
                        line_start=child_offset,
                        line_end=child_offset,
                        unit_kind=child_kind,
                        unit_name=child_name,
                        parent_unit=name,
                        is_data_setup=True,
                        purpose_hints=_purpose_hints(language, child_kind, child_stripped, name=child_name),
                    )
                )
        i = max(end, i + 1)
    return segments


def _json_segments(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except Exception:
        return _config_segments(text, "json")
    if not isinstance(data, (dict, list)):
        return _config_segments(text, "json")
    return _config_segments(json.dumps(data, ensure_ascii=True, indent=2), "json")


def _yaml_segments(text: str) -> list[dict[str, Any]]:
    return _config_segments(text, "yaml")


def _sql_segments(text: str) -> list[dict[str, Any]]:
    """SQL metnini statement ve clause duzeyinde okunabilir segmentlere bol."""
    lines = str(text or "").splitlines()
    segments = _iter_comment_segments(lines, "sql")
    start = 0
    while start < len(lines):
        while start < len(lines) and not lines[start].strip():
            start += 1
        if start >= len(lines):
            break
        end = start + 1
        while end < len(lines):
            if ";" in lines[end - 1]:
                break
            end += 1
            if end - start >= 40:
                break
        statement_text = _slice_lines(lines, start + 1, end)
        if not _normalize_ws(statement_text):
            start = max(end, start + 1)
            continue
        clause_groups = _sql_clause_groups(statement_text, statement_start_line=start + 1)
        first_line = next((ln for ln in statement_text.splitlines() if ln.strip()), "")
        kind = clause_groups[0][0] if clause_groups else _generic_kind(first_line, "sql")
        if kind == "sql_statement":
            kind = "sql_statement"
        statement_name = _extract_sql_segment_name(statement_text, kind) or f"statement_{start + 1}"
        segments.append(
            _segment(
                text=statement_text,
                line_start=start + 1,
                line_end=end,
                unit_kind=kind,
                unit_name=statement_name,
                purpose_hints=_purpose_hints("sql", kind, statement_text, name=statement_name),
            )
        )
        for clause_kind, clause_lines in clause_groups:
            clause_text = "\n".join(item[1] for item in clause_lines).strip()
            if (
                clause_kind == kind
                and clause_lines[0][0] == start + 1
                and clause_lines[-1][0] == end
                and _normalize_ws(clause_text) == _normalize_ws(statement_text)
            ):
                continue
            clause_name = _extract_sql_segment_name(clause_text, clause_kind) or clause_kind.replace("sql_", "")
            segments.append(
                _segment(
                    text=clause_text,
                    line_start=clause_lines[0][0],
                    line_end=clause_lines[-1][0],
                    unit_kind=clause_kind,
                    unit_name=clause_name,
                    parent_unit=statement_name,
                    purpose_hints=_purpose_hints("sql", clause_kind, clause_text, name=clause_name),
                )
            )
        start = max(end, start + 1)
    return segments


def build_code_segments(text: str, language: str) -> list[dict[str, Any]]:
    """Dil tipine gore en uygun segmentleyiciyi secip tekrarli kayitlari temizler."""
    if language == "python":
        segments = _python_segments(text)
    elif language == "json":
        segments = _json_segments(text)
    elif language == "yaml":
        segments = _yaml_segments(text)
    elif language == "sql":
        segments = _sql_segments(text)
    else:
        segments = _generic_segments(text, language)
    if not segments:
        # Parser hicbir anlamli unit bulamazsa line-window fallback'i ile ingestion akisinin bos kalmasini onler.
        lines = str(text or "").splitlines()
        for start in range(0, len(lines), 24):
            line_start = start + 1
            line_end = min(len(lines), start + 24)
            block_text = _slice_lines(lines, line_start, line_end)
            if _normalize_ws(block_text):
                segments.append(_segment(text=block_text, line_start=line_start, line_end=line_end, unit_kind="block"))
    out = []
    seen = set()
    for segment in sorted(segments, key=lambda item: (int(item.get("line_start") or 0), int(item.get("line_end") or 0), str(item.get("unit_kind") or ""), str(item.get("unit_name") or ""))):
        text_key = _normalize_ws(segment.get("text") or "")
        if not text_key:
            continue
        key = (int(segment.get("line_start") or 0), int(segment.get("line_end") or 0), str(segment.get("unit_kind") or ""), str(segment.get("unit_name") or ""), text_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(segment)
    return out


def build_code_chunk_title(language: str, unit_kind: str, unit_name: str, parent_unit: str, line_start: int, line_end: int) -> str:
    """Segment metasini kullanarak explain ve retrieval icin okunabilir chunk basligi olusturur."""
    label_map = {
        "import": "import",
        "constant": "sabit",
        "variable": "degisken",
        "function": "fonksiyon",
        "class": "sinif",
        "method": "method",
        "test_function": "test",
        "assertion": "assert",
        "api_call": "api",
        "control_flow": "akis",
        "comment": "yorum",
        "docstring": "docstring",
        "test_step": "test_step",
        "section": "section",
        "config_entry": "config",
        "style_rule": "stil",
        "markup_block": "markup",
        "script_block": "script",
        "style_block": "style",
        "sql_with": "with",
        "sql_select": "select",
        "sql_from_join": "from_join",
        "sql_where": "where",
        "sql_where_group": "where_group",
        "sql_group_by": "group_by",
        "sql_order_by": "order_by",
        "sql_set": "set",
        "sql_insert": "insert",
        "sql_update": "update",
        "sql_delete": "delete",
        "sql_create": "create",
        "sql_alter": "alter",
        "command": "komut",
        "block": "blok",
    }
    label = label_map.get(unit_kind, unit_kind or "blok")
    name = unit_name or parent_unit or f"{label}:{line_start}-{line_end}"
    return f"{language} {label} {name}".strip()
