"""Deterministic Delivery Assurance Agent.

This module implements a governance-focused WSR analyzer with strict rules:
- Exclude SLA and Appendix content.
- Exclude closed/resolved and fully-controlled items from active risk output.
- Prefer section-based extraction when explicit sections exist.
- Fall back to one consolidated signal in unstructured reports.
- Produce fixed markdown sections/tables for audit-ready consumption.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


@dataclass
class RunMetadata:
    """Run-level input metadata provided by caller/UI."""

    project_id: str
    week_date: str  # YYYY-MM-DD


@dataclass
class ParsedDocument:
    """Canonical parsed document shape used by downstream engines."""

    project_name: str
    reporting_date: str
    sections: Dict[str, str]
    raw_text: str


RISK_SCAN_KEYWORDS = [
    "delay",
    "blocked",
    "dependency",
    "pending",
    "quality impact",
    "defect leakage",
    "resource constraint",
    "risk",
    "issue",
]

SLA_PATTERNS = [
    r"\bsla\b",
    r"service level",
    r"breach",
    r"ticket sla",
    r"contractual sla",
    r"compliance metric",
]


def _read_pdf(path: str) -> str:
    """Extract raw text from each PDF page while preserving page markers."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    out: List[str] = []
    for i, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        if txt:
            out.append(f"[PAGE {i}]\n{txt}")
    return "\n\n".join(out)


def _read_docx(path: str) -> str:
    """Extract paragraph and table text from DOCX files."""
    from docx import Document

    doc = Document(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    table_rows: List[str] = []

    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                table_rows.append(" | ".join(cells))

    if table_rows:
        paragraphs.append("[TABLES]\n" + "\n".join(table_rows))
    return "\n".join(paragraphs)


def _read_txt(path: str) -> str:
    """Read plain-text WSR content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_wsr_file(path: str) -> str:
    """Route file extraction by extension (PDF/DOCX/TXT)."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return _read_pdf(path)
    if lower.endswith(".docx"):
        return _read_docx(path)
    if lower.endswith(".txt"):
        return _read_txt(path)
    raise ValueError("Unsupported input type. Allowed: PDF, DOCX, TXT.")


def _remove_appendix(text: str) -> str:
    """Drop appendix section and everything after it (strict rule)."""
    lines = text.splitlines()
    cut = None
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(appendix|appendices|annexure)\b", ln, flags=re.IGNORECASE):
            cut = i
            break
    if cut is not None:
        lines = lines[:cut]
    return "\n".join(lines)


def _remove_sla_lines(lines: List[str]) -> List[str]:
    """Remove lines containing SLA-related terms (global exclusion)."""
    filtered: List[str] = []
    for ln in lines:
        if any(re.search(p, ln, flags=re.IGNORECASE) for p in SLA_PATTERNS):
            continue
        filtered.append(ln)
    return filtered


def clean_text(text: str) -> str:
    """Normalize whitespace and apply hard exclusions before analysis."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _remove_appendix(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    lines = _remove_sla_lines(lines)
    return "\n".join(lines).strip()


def _extract_section(text: str, names: List[str], stop_names: List[str]) -> str:
    """Extract content under a heading until next known heading."""
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if any(re.match(rf"^{n}\s*:?,?\s*$", ln.strip().lower()) for n in names)]
    if not starts:
        return ""

    start = starts[0] + 1
    end = len(lines)
    for i in range(start, len(lines)):
        low = lines[i].strip().lower()
        if any(re.match(rf"^{sn}\s*:?,?\s*$", low) for sn in stop_names):
            end = i
            break

    section_lines = _remove_sla_lines(lines[start:end])
    return "\n".join(section_lines).strip()


def process_document(raw_text: str, metadata: RunMetadata) -> ParsedDocument:
    """Build normalized sections and reporting date from raw WSR text."""
    cleaned = clean_text(raw_text)

    stop = [
        "summary",
        "executive summary",
        "milestones",
        "progress",
        "risks",
        "issues",
        "dependencies",
        "next steps",
        "highlights",
        "actions",
    ]

    sections = {
        "summary": _extract_section(cleaned, ["summary", "executive summary"], stop),
        "milestones": _extract_section(cleaned, ["milestones", "progress", "key milestones"], stop),
        "risks": _extract_section(cleaned, ["risks", "issues", "risk & issues", "concerns"], stop),
        "dependencies": _extract_section(cleaned, ["dependencies", "external dependencies", "assumptions"], stop),
        "others": cleaned,
    }

    date_match = re.search(r"(20\d{2}[-/]\d{2}[-/]\d{2})", cleaned)
    reporting_date = date_match.group(1).replace("/", "-") if date_match else metadata.week_date

    return ParsedDocument(
        project_name=metadata.project_id,
        reporting_date=reporting_date,
        sections=sections,
        raw_text=cleaned,
    )


def _extract_lines(text: str) -> List[str]:
    """Split section body into clean bullet-like lines."""
    return [ln.strip("-• ") for ln in text.splitlines() if ln.strip("-• ").strip()]


def _is_closed(text: str) -> bool:
    """Check if item is explicitly marked closed/resolved/completed/done."""
    return bool(re.search(r"\b(closed|resolved|completed|done)\b", text, flags=re.IGNORECASE))


def _has_control_triplet(text: str) -> bool:
    """Check whether Owner + Mitigation + Due/ETA are all present."""
    owner = bool(re.search(r"owner\s*[:\-]", text, flags=re.IGNORECASE))
    mitigation = bool(re.search(r"mitigation\s*[:\-]", text, flags=re.IGNORECASE))
    due = bool(re.search(r"(20\d{2}[-/]\d{2}[-/]\d{2}|eta\s*[:\-])", text, flags=re.IGNORECASE))
    return owner and mitigation and due


def detect_risks_and_dependencies(parsed: ParsedDocument) -> Tuple[List[Dict[str, str]], str, List[str]]:
    """
    Returns: (active_items, detection_mode, controlled_monitoring_items)
    active_items include only uncontrolled/partially controlled and non-closed items.
    """

    active: List[Dict[str, str]] = []
    controlled_monitor: List[str] = []

    explicit_risk_section = bool(parsed.sections.get("risks"))
    explicit_dep_section = bool(parsed.sections.get("dependencies"))

    if explicit_risk_section or explicit_dep_section:
        # Structured mode: only parse explicit risk/dependency sections.
        mode = "structured"

        for ln in _extract_lines(parsed.sections.get("risks", "")):
            if _is_closed(ln):
                continue
            if _has_control_triplet(ln):
                controlled_monitor.append(ln)
                continue
            active.append({"type": "Risk", "text": ln})

        for ln in _extract_lines(parsed.sections.get("dependencies", "")):
            if _is_closed(ln):
                continue
            if _has_control_triplet(ln):
                controlled_monitor.append(ln)
                continue
            active.append({"type": "Dependency", "text": ln})

        return active, mode, controlled_monitor

    # Unstructured mode: create only one consolidated signal from keyword scan.
    mode = "unstructured"
    hits: List[str] = []
    for ln in parsed.raw_text.splitlines():
        low = ln.lower()
        if any(k in low for k in RISK_SCAN_KEYWORDS):
            if _is_closed(ln):
                continue
            hits.append(ln.strip())

    if not hits:
        return [], mode, []

    consolidated = " ; ".join(hits[:3])
    consolidated_type = "Dependency" if "dependency" in consolidated.lower() else "Risk"
    if not _has_control_triplet(consolidated):
        active.append({"type": consolidated_type, "text": consolidated})

    return active, mode, []


def _build_llm() -> ChatOpenAI:
    """Create deterministic LLM parser client (temperature=0)."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for LLM parser mode.")
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _latest_date(text: str) -> str:
    """Return latest date mentioned in a string; otherwise N/A."""
    dates = re.findall(r"(20\d{2}[-/]\d{2}[-/]\d{2})", text)
    if not dates:
        return "N/A"
    normalized = [d.replace("/", "-") for d in dates]
    try:
        return max(normalized, key=lambda d: datetime.strptime(d, "%Y-%m-%d"))
    except ValueError:
        return normalized[-1]


def _rule_parse_item(item_type: str, text: str, week_date: str) -> Dict[str, str]:
    """Rule-based fallback parser for a risk/dependency line."""
    status_match = re.search(r"status\s*[:\-]\s*([^,;|]+)", text, flags=re.IGNORECASE)
    status = status_match.group(1).strip() if status_match else "N/A"

    owner_match = re.search(r"owner\s*[:\-]\s*([^,;|]+)", text, flags=re.IGNORECASE)
    owner = owner_match.group(1).strip() if owner_match else "N/A"

    mitigation_match = re.search(r"mitigation\s*[:\-]\s*([^|]+)", text, flags=re.IGNORECASE)
    mitigation = mitigation_match.group(1).strip() if mitigation_match else "Missing/Vague"

    due_date = _latest_date(text)

    identified_match = re.search(r"(identified|created)\s*(on)?\s*[:\-]?\s*(20\d{2}[-/]\d{2}[-/]\d{2})", text, flags=re.IGNORECASE)
    ageing = "N/A"
    if identified_match:
        id_date = identified_match.group(3).replace("/", "-")
        try:
            d0 = datetime.strptime(id_date, "%Y-%m-%d")
            d1 = datetime.strptime(week_date, "%Y-%m-%d")
            ageing = str((d1 - d0).days)
        except ValueError:
            ageing = "N/A"

    impact_t = re.search(r"timeline|schedule|delay|slippage", text, flags=re.IGNORECASE)
    impact_q = re.search(r"quality|defect|rework", text, flags=re.IGNORECASE)
    if impact_t and impact_q:
        impact = "Both"
    elif impact_t:
        impact = "Timeline"
    elif impact_q:
        impact = "Quality"
    else:
        impact = "N/A"

    return {
        "type": item_type,
        "description": text,
        "risk_status": status,
        "risk_ageing": ageing,
        "owner": owner,
        "due_date": due_date,
        "mitigation": mitigation,
        "impact": impact,
        "source": "**Current WSR**",
    }


def parse_items_with_llm_or_rules(items: List[Dict[str, str]], week_date: str, allow_llm: bool = True) -> List[Dict[str, str]]:
    """Parse detected items into normalized schema using LLM then rules fallback."""
    if not items:
        return []

    if allow_llm:
        try:
            llm = _build_llm()
            parser = JsonOutputParser()
            resp = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are a strict extraction parser. "
                            "Return JSON with key items[] with fields: type,description,risk_status,risk_ageing,owner,due_date,mitigation,impact. "
                            "Use only explicit facts. If missing, use N/A."
                        )
                    ),
                    HumanMessage(content=json.dumps({"week_date": week_date, "items": items})),
                ]
            )
            parsed = parser.parse(resp.content)
            out = parsed.get("items", [])
            if isinstance(out, list) and out:
                refined: List[Dict[str, str]] = []
                for itm in out:
                    merged = {
                        "type": itm.get("type", "Risk"),
                        "description": itm.get("description", "N/A"),
                        "risk_status": itm.get("risk_status", "N/A"),
                        "risk_ageing": itm.get("risk_ageing", "N/A"),
                        "owner": itm.get("owner", "N/A"),
                        "due_date": itm.get("due_date", "N/A"),
                        "mitigation": itm.get("mitigation", "Missing/Vague"),
                        "impact": itm.get("impact", "N/A"),
                        "source": "**Current WSR**",
                    }
                    refined.append(merged)
                return refined
        except Exception:
            pass

    return [_rule_parse_item(i["type"], i["text"], week_date) for i in items]


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed texts for semantic previous-week comparison."""
    emb = OpenAIEmbeddings(model="text-embedding-3-small")
    return emb.embed_documents(texts)


def _cos(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _norm(value: str) -> str:
    """Normalize optional string fields for deterministic comparison."""
    return (value or "N/A").strip().lower()


def _has_explicit_progress(current: Dict[str, str], previous: Dict[str, str]) -> bool:
    """Return True only when explicit field-level evidence of progress exists.

    This function intentionally avoids semantic guessing. We only mark "Progress update"
    when structured fields changed in the current WSR compared to previous week.
    """
    status_changed = _norm(current.get("risk_status")) != _norm(previous.get("risk_status"))

    mitigation_current = _norm(current.get("mitigation", "Missing/Vague"))
    mitigation_previous = _norm(previous.get("mitigation", "Missing/Vague"))
    mitigation_improved = mitigation_previous in {"missing/vague", "n/a"} and mitigation_current not in {
        "missing/vague",
        "n/a",
    }

    due_changed = _norm(current.get("due_date")) != _norm(previous.get("due_date"))
    owner_changed = _norm(current.get("owner")) != _norm(previous.get("owner"))

    return status_changed or mitigation_improved or due_changed or owner_changed


def _best_similarity_match(current_vec: List[float], previous_vecs: List[List[float]]) -> Tuple[float, int]:
    """Return top semantic match score and index for a current description."""
    sims = [(_cos(current_vec, p), j) for j, p in enumerate(previous_vecs)]
    sims.sort(reverse=True)
    return sims[0]


def _token_overlap_score(left: str, right: str) -> float:
    """Fallback lexical similarity when embeddings are unavailable."""
    left_tokens = {t for t in re.findall(r"[a-z0-9]+", left.lower()) if len(t) > 2}
    right_tokens = {t for t in re.findall(r"[a-z0-9]+", right.lower()) if len(t) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def compare_with_previous(current_items: List[Dict[str, str]], previous_items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Classify week-over-week state using vector matching + explicit progress signals.

    Matching strategy:
    1) Vector similarity (embedding-based) to pair likely same underlying item.
    2) Deterministic field checks to decide Progress vs Stagnant.
    3) Unmatched current => Newly introduced; unmatched previous => Risk closed.
    """
    cur = [x.get("description", "") for x in current_items]
    prev = [x.get("description", "") for x in previous_items]

    if not cur and not prev:
        return []
    if not prev:
        return [{"item": c, "comparison": "Newly introduced"} for c in cur]
    if not cur:
        return [{"item": p, "comparison": "Risk closed"} for p in prev]

    use_embeddings = True
    try:
        cv = _embed_texts(cur)
        pv = _embed_texts(prev)
    except Exception:
        use_embeddings = False
        cv = []
        pv = []

    used_prev = set()
    out: List[Dict[str, str]] = []

    for i, c in enumerate(cur):
        if use_embeddings:
            score, j = _best_similarity_match(cv[i], pv)
            matched = score >= 0.84
        else:
            lexical = sorted([(_token_overlap_score(c, p), j) for j, p in enumerate(prev)], reverse=True)
            score, j = lexical[0]
            matched = score >= 0.40

        if not matched:
            out.append({"item": c, "comparison": "Newly introduced"})
            continue

        used_prev.add(j)
        if _has_explicit_progress(current_items[i], previous_items[j]):
            out.append({"item": c, "comparison": "Progress update"})
        else:
            out.append({"item": c, "comparison": "Stagnant risk"})

    for j, p in enumerate(prev):
        if j not in used_prev:
            out.append({"item": p, "comparison": "Risk closed"})

    return out


def _is_date_older(date_str: str, week_date: str) -> bool:
    """Return True when due date is older than WSR date."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") < datetime.strptime(week_date, "%Y-%m-%d")
    except ValueError:
        return False


def reporting_gaps(items: List[Dict[str, str]], week_date: str) -> Tuple[List[str], List[str]]:
    """Find factual reporting gaps and cap suggestions to <=25% of factual findings."""
    factual: List[str] = []
    suggestions: List[str] = []

    for it in items:
        desc = it.get("description", "N/A")
        if it.get("owner", "N/A") in {"", "N/A"}:
            factual.append(f"Missing owner: {desc}")

        due = it.get("due_date", "N/A")
        if due in {"", "N/A"}:
            factual.append(f"Missing/undefined due date: {desc}")
        elif _is_date_older(due, week_date):
            factual.append(f"Due date older than WSR date: {desc}")

        mitigation = (it.get("mitigation", "Missing/Vague") or "Missing/Vague").strip().lower()
        if mitigation in {"missing/vague", "missing", "vague", "n/a", "tbd"} or len(mitigation.split()) <= 3:
            factual.append(f"Missing or vague mitigation: {desc}")

        if it.get("type", "Risk") == "Dependency":
            if it.get("owner", "N/A") in {"", "N/A"} or it.get("due_date", "N/A") in {"", "N/A"}:
                factual.append(f"Dependency without ownership/action/timeline: {desc}")

    if factual:
        suggestions.extend(
            [
                "Use a standard risk template: Owner, Mitigation, Due Date, Status for every open item.",
                "Track dependency ETA weekly and link each dependency to a named owner.",
            ]
        )

    # max 25% suggestions
    max_suggestions = max(0, len(factual) // 3)
    suggestions = suggestions[:max_suggestions]

    return factual, suggestions


def build_summary(parsed_current: ParsedDocument, items: List[Dict[str, str]], comparisons: List[Dict[str, str]]) -> List[str]:
    """Create concise 4-5 bullet delivery summary from factual signals."""
    bullets: List[str] = []

    milestone_lines = _extract_lines(parsed_current.sections.get("milestones", ""))[:2]
    for m in milestone_lines:
        bullets.append(f"Milestone update: {m}")

    if items:
        bullets.append(f"Detected {len(items)} active uncontrolled/partially controlled risk/dependency item(s) in current WSR.")

    progress = [c for c in comparisons if c["comparison"] == "Progress update"]
    stagnant = [c for c in comparisons if c["comparison"] == "Stagnant risk"]
    new_items = [c for c in comparisons if c["comparison"] == "Newly introduced"]

    if progress:
        bullets.append(f"{len(progress)} item(s) show progress versus previous week.")
    if stagnant:
        bullets.append(f"{len(stagnant)} item(s) remain stagnant across weeks and may need escalation.")
    if new_items:
        bullets.append(f"{len(new_items)} new item(s) introduced this week.")

    if not bullets:
        return ["Not enough information."]

    return bullets[:5]


def generate_risk_portal_entries(current_items: List[Dict[str, str]], comparisons: List[Dict[str, str]]) -> List[str]:
    """Create portal entries only for risks active across consecutive weeks."""
    recurring = {c["item"] for c in comparisons if c["comparison"] in {"Stagnant risk", "Progress update"}}
    entries: List[str] = []
    for it in current_items:
        desc = it.get("description", "")
        if desc in recurring:
            impact = it.get("impact", "delivery")
            entries.append(f"Due to {desc}, there will be impact on {impact}.")
    return entries


def _table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a markdown table with deterministic empty-state fallback."""
    if not rows:
        return "No data available for this section."
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([head, sep] + body)


def _enforce_no_sla(text: str) -> str:
    """Final safety pass to remove any SLA remnants from output."""
    lines = text.splitlines()
    keep = _remove_sla_lines(lines)
    return "\n".join(keep)


def format_markdown_output(
    metadata: RunMetadata,
    summary_bullets: List[str],
    controlled_monitor: List[str],
    current_items: List[Dict[str, str]],
    comparisons: List[Dict[str, str]],
    gaps_factual: List[str],
    gaps_suggestions: List[str],
    risk_portal_entries: List[str],
) -> str:
    """Build strict markdown output with required section order and table schema."""
    if not current_items:
        risk_rows = [["No Risk in Current WSR", "N/A", "N/A", "N/A", "**Current WSR**"]]
    else:
        risk_rows = [
            [
                i.get("type", "Risk"),
                i.get("description", "N/A"),
                i.get("risk_status", "N/A"),
                i.get("risk_ageing", "N/A"),
                i.get("source", "**Current WSR**"),
            ]
            for i in current_items
        ]

    comparison_rows = [[c.get("item", "N/A"), c.get("comparison", "N/A")] for c in comparisons] or [["N/A", "No data available for this section."]]
    gap_rows = [[g] for g in gaps_factual] + [[f"Suggestion: {s}"] for s in gaps_suggestions]
    if not gap_rows:
        gap_rows = [["No data available for this section."]]

    portal_rows = [[e] for e in risk_portal_entries] or [["No data available for this section."]]

    lines: List[str] = []
    lines.append("## High Level Analysis")
    lines.append(f"- Project Name: {metadata.project_id}")
    lines.append(f"- WSR Reporting Date: {metadata.week_date}")
    for b in summary_bullets:
        lines.append(f"- {b}")

    if controlled_monitor:
        lines.append("- Risks Requiring Close Monitoring:")
        for c in controlled_monitor:
            lines.append(f"  - {c}")

    lines.append("")
    lines.append("## Risks & Dependencies")
    lines.append(_table(["Risk/Dependency", "Description", "Risk Status", "Risk Ageing", "Source"], risk_rows))

    lines.append("")
    lines.append("## Progress Comparison from Previous Week")
    lines.append(_table(["Item", "Comparison"], comparison_rows))

    lines.append("")
    lines.append("## Reporting Gaps")
    lines.append(_table(["Gap / Observation"], gap_rows))

    lines.append("")
    lines.append("## Risks to Track in Risk Portal")
    lines.append(_table(["Entry"], portal_rows))

    markdown = "\n".join(lines).strip() + "\n"
    markdown = _enforce_no_sla(markdown)
    return markdown


def run_delivery_assurance(current_wsr_path: str, previous_wsr_path: str, metadata: RunMetadata) -> Dict[str, Any]:
    """Execute end-to-end deterministic analysis for current vs previous WSR."""
    current_raw = read_wsr_file(current_wsr_path)
    previous_raw = read_wsr_file(previous_wsr_path)

    current_doc = process_document(current_raw, metadata)
    previous_doc = process_document(previous_raw, metadata)

    current_detected, mode, controlled_monitor = detect_risks_and_dependencies(current_doc)
    previous_detected, _, _ = detect_risks_and_dependencies(previous_doc)

    # Keep cost deterministic: <=2 LLM calls per run (current + previous parser pass).
    current_items = parse_items_with_llm_or_rules(current_detected, metadata.week_date, allow_llm=True)
    previous_items = parse_items_with_llm_or_rules(previous_detected, metadata.week_date, allow_llm=True)

    comparisons = compare_with_previous(current_items, previous_items)
    gaps_factual, gaps_suggestions = reporting_gaps(current_items, metadata.week_date)
    summary = build_summary(current_doc, current_items, comparisons)
    risk_portal_entries = generate_risk_portal_entries(current_items, comparisons)

    markdown = format_markdown_output(
        metadata=metadata,
        summary_bullets=summary,
        controlled_monitor=controlled_monitor,
        current_items=current_items,
        comparisons=comparisons,
        gaps_factual=gaps_factual,
        gaps_suggestions=gaps_suggestions,
        risk_portal_entries=risk_portal_entries,
    )

    return {
        "project_name": metadata.project_id,
        "wsr_reporting_date": metadata.week_date,
        "detection_mode": mode,
        "current_items": current_items,
        "previous_items": previous_items,
        "comparisons": comparisons,
        "reporting_gaps": {"factual": gaps_factual, "suggestions": gaps_suggestions},
        "risk_portal_entries": risk_portal_entries,
        "markdown": markdown,
    }
