"""Delivery assurance orchestration for week-over-week WSR review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .workflow import analyze_wsr_file


@dataclass
class RunMetadata:
    """Run-level metadata for week-over-week assurance analysis."""

    project_id: str
    week_date: str
    account: str = "N/A"


def _token_set(text: str) -> set[str]:
    return {token.lower() for token in text.split() if len(token) > 2}


def _best_match(current: str, previous_candidates: List[str]) -> tuple[float, str]:
    cur = _token_set(current)
    best_score = 0.0
    best_text = ""
    for candidate in previous_candidates:
        prev = _token_set(candidate)
        if not cur or not prev:
            continue
        score = len(cur.intersection(prev)) / max(1, len(cur.union(prev)))
        if score > best_score:
            best_score = score
            best_text = candidate
    return best_score, best_text


def _progress_comparison(current_items: List[Dict[str, str]], previous_items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Compare current vs previous items using deterministic token overlap."""
    previous_descriptions = [item["description"] for item in previous_items]
    output: List[Dict[str, str]] = []

    matched_previous = set()
    for item in current_items:
        score, match = _best_match(item["description"], previous_descriptions)
        if score >= 0.45:
            matched_previous.add(match)
            status = "Existing (updated wording)" if item["description"] != match else "Existing (same signal)"
            output.append({"current": item["description"], "previous": match, "status": status})
        else:
            output.append({"current": item["description"], "previous": "N/A", "status": "New signal"})

    for previous in previous_descriptions:
        if previous not in matched_previous:
            output.append({"current": "N/A", "previous": previous, "status": "No longer reported"})

    return output


def run_delivery_assurance(current_wsr_path: str, previous_wsr_path: str, metadata: RunMetadata) -> Dict[str, Any]:
    """Run systematic week-over-week delivery assurance analysis."""
    current = analyze_wsr_file(
        file_path=current_wsr_path,
        account=metadata.account,
        project_name=metadata.project_id,
        week_date=metadata.week_date,
    )
    previous = analyze_wsr_file(
        file_path=previous_wsr_path,
        account=metadata.account,
        project_name=metadata.project_id,
        week_date=metadata.week_date,
    )

    current_items = current["analysis"]["risks"] + current["analysis"]["dependencies"]
    previous_items = previous["analysis"]["risks"] + previous["analysis"]["dependencies"]

    return {
        "project_id": metadata.project_id,
        "week_date": metadata.week_date,
        "account": metadata.account,
        "current_week_analysis": current,
        "previous_week_analysis": previous,
        "progress_comparison": _progress_comparison(current_items=current_items, previous_items=previous_items),
    }
