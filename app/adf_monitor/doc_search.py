"""Retrieval over a local *referenced* Microsoft Learn knowledge index.

This is lexical evidence retrieval (BM25), NOT a hardcoded error-to-answer map.
The index contains original short French paraphrases with canonical source URLs.
It is versioned and curated; it does not scrape the web at runtime.
"""

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

INDEX_FILE = Path(__file__).resolve().parents[2] / "docs" / "microsoft_adf_index.json"
MAX_QUERY_LENGTH = 500


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9_]+", normalized)


def load_index(index_file: Path | None = None) -> list[dict]:
    path = index_file or INDEX_FILE
    contents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(contents, list):
        raise TypeError("Invalid documentation index")
    records = []
    for raw in contents[:100]:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url", "")
        if not isinstance(url, str) or not url.startswith(
            "https://learn.microsoft.com/"
        ):
            continue
        if not isinstance(raw.get("codes"), list):
            continue
        records.append(raw)
    return records


def search_official_docs(
    query: str,
    *,
    error_code: str | None = None,
    limit: int = 3,
    index_file: Path | None = None,
) -> list[dict]:
    """Retrieve ranked official references; exact error codes take precedence."""
    if not isinstance(query, str) or len(query) > MAX_QUERY_LENGTH:
        raise ValueError("Invalid search query")
    if not 1 <= limit <= 5:
        raise ValueError("Invalid limit")
    if error_code is not None and not re.fullmatch(r"[A-Za-z0-9_]{1,80}", error_code):
        raise ValueError("Invalid error code")

    records = load_index(index_file)
    if not records:
        return []
    code = error_code.upper() if error_code else None
    if code:
        # Code-specific documentation must *actually mention* that code.
        # Otherwise return no specific guidance instead of a plausible guess.
        records = [doc for doc in records if code in doc["codes"]]
        if not records:
            return []

    documents = [
        tokens(" ".join([
            str(d.get("title", "")),
            str(d.get("summary_fr", "")),
            " ".join(d.get("keywords", [])),
            str(d.get("service", "")),
        ]))
        for d in records
    ]
    avg_len = sum(len(x) for x in documents) / len(documents) or 1
    doc_freq = Counter(word for words in documents for word in set(words))
    query_words = tokens(query)
    if not code and not query_words:
        return []
    scores = []
    n = len(documents)
    for doc, words in zip(records, documents, strict=True):
        counts = Counter(words)
        score = 0.0
        for word in set(query_words):
            freq = counts[word]
            if not freq:
                continue
            idf = math.log(1 + (n - doc_freq[word] + 0.5) / (doc_freq[word] + 0.5))
            score += idf * (freq * 2.2) / (
                freq + 1.2 * (0.25 + 0.75 * len(words) / avg_len)
            )
        if code:
            score += 100
        if score > 0:
            scores.append((score, doc))

    scores.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {
            "doc_id": doc["id"],
            "title": doc["title"],
            "url": doc["url"],
            "summary_fr": doc["summary_fr"],
            "checks_fr": doc["checks_fr"][:5],
            "matched_error_code": code if code else None,
            "source_type": "MICROSOFT_LEARN_CURATED_SUMMARY",
            "retrieval_score": round(score, 4),
        }
        for score, doc in scores[:limit]
    ]
