import json
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_text


def load_jsonl(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_jsonl_dir(directory: Path) -> List[Dict]:
    records = []
    for path in sorted(directory.glob("*.jsonl")):
        records.extend(load_jsonl(path))
    return records


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def build_fake_cache(mitre: MitreHelper) -> Dict[str, Dict]:
    cache = {}
    for technique in mitre.get_techniques():
        technique_id = technique.get("id")
        # Extract external_id from references
        external_id = ""
        for ref in technique.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                external_id = ref.get("external_id", "")
                break

        cache[technique_id] = {
            "external_id": external_id,
            "name": technique.get("name", ""),
            "text": build_technique_text(
                {
                    "external_id": external_id,
                    "name": technique.get("name", ""),
                    "description": technique.get("description", ""),
                }
            ),
            "embedding": [],
            "dimension": 0,
        }
    return cache


def fake_semantic_search(
    query: str,
    cache: Dict[str, Dict],
    top_k: int = 10,
    min_score: float = 0.0,
) -> List[Tuple[str, str, str, float]]:
    query_tokens = set(tokenize(query))
    scored = []
    for technique_id, data in cache.items():
        technique_tokens = set(tokenize(data.get("text", "")))
        overlap = len(query_tokens & technique_tokens)
        denominator = len(query_tokens | technique_tokens) or 1
        score = overlap / denominator
        if score >= min_score:
            scored.append(
                (
                    technique_id,
                    data.get("external_id", ""),
                    data.get("name", ""),
                    score,
                )
            )
    scored.sort(key=lambda item: item[3], reverse=True)
    return scored[:top_k]


def accepted_ids(record: Dict) -> set:
    return set(record.get("expected_ids", [])) | set(record.get("allowed_ids", []))


def top_k_hit(record: Dict, results: Sequence[Dict], k: int) -> bool:
    accepted = accepted_ids(record)
    top_ids = [result.get("external_id") for result in results[:k]]
    return bool(accepted.intersection(top_ids))


def recall_at_k(record: Dict, results: Sequence[Dict], k: int) -> float:
    expected = set(record.get("expected_ids", []))
    if not expected:
        return 0.0
    top_ids = {result.get("external_id") for result in results[:k]}
    return len(expected.intersection(top_ids)) / len(expected)


def tactic_match(record: Dict, results: Sequence[Dict], k: int) -> bool:
    expected_tactics = set(record.get("expected_tactics", []))
    if not expected_tactics:
        return True
    top_tactics = set()
    for result in results[:k]:
        top_tactics.update(result.get("tactics", []))
    return bool(expected_tactics.intersection(top_tactics))


def evaluate_records(
    records: Iterable[Dict],
    search_fn: Callable[[str], List[Dict]],
) -> Dict[str, float]:
    records = list(records)
    scored_records = [record for record in records if record.get("expected_ids")]
    if not scored_records:
        return {
            "total_records": len(records),
            "scored_records": 0,
            "top1_accuracy": 0.0,
            "top3_accuracy": 0.0,
            "recall_at_5": 0.0,
            "tactic_match_rate": 0.0,
        }

    top1_hits = 0
    top3_hits = 0
    recall_sum = 0.0
    tactic_hits = 0

    for record in scored_records:
        results = search_fn(record["query"])
        if top_k_hit(record, results, 1):
            top1_hits += 1
        if top_k_hit(record, results, 3):
            top3_hits += 1
        recall_sum += recall_at_k(record, results, 5)
        if tactic_match(record, results, 5):
            tactic_hits += 1

    total = len(scored_records)
    return {
        "total_records": len(records),
        "scored_records": total,
        "top1_accuracy": top1_hits / total,
        "top3_accuracy": top3_hits / total,
        "recall_at_5": recall_sum / total,
        "tactic_match_rate": tactic_hits / total,
    }
