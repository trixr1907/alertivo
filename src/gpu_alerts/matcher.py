from __future__ import annotations

import hashlib
import re
import unicodedata

from gpu_alerts.models import MatchResult


GENERIC_MODEL_STOPWORDS = {
    "der",
    "die",
    "das",
    "mit",
    "fur",
    "und",
    "inkl",
    "neu",
    "new",
    "bundle",
    "edition",
}


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = normalized.replace("™", " ").replace("-", " ").replace("/", " ")
    normalized = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", normalized)
    normalized = re.sub(r"\b16\s*gb\b|\bgddr\s*7\b|\bgddr\b|\bgeforce\b|\bgb\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _fallback_hash(normalized_title: str) -> str:
    return hashlib.sha1(normalized_title.encode("utf-8")).hexdigest()[:12]


def _normalized_compact(value: str) -> str:
    return normalize_title(value).replace(" ", "")


def _unique_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        normalized = normalize_title(value)
        if not normalized:
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms


class ProductMatcher:
    def match(self, title: str, product_hint: str | None = None, *, include_terms: list[str] | None = None) -> MatchResult | None:
        normalized = normalize_title(title)
        if not normalized:
            return None

        family = (product_hint or "").strip()
        if not family:
            return None

        match_terms = self._resolve_match_terms(product_hint=family, include_terms=include_terms)
        if not match_terms:
            return None

        compact_title = normalized.replace(" ", "")
        if not all(self._term_present(term, normalized, compact_title) for term in match_terms):
            return None

        return MatchResult(
            product_family=family,
            canonical_model=self._build_generic_model_key(family, normalized, match_terms),
            normalized_title=normalized,
        )

    def _resolve_match_terms(self, *, product_hint: str, include_terms: list[str] | None) -> list[str]:
        explicit_terms = _unique_terms(include_terms or [])
        if explicit_terms:
            return explicit_terms

        normalized_hint = normalize_title(product_hint)
        tokens = [token for token in normalized_hint.split() if token and token not in GENERIC_MODEL_STOPWORDS]
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _term_present(term: str, normalized_title: str, compact_title: str) -> bool:
        if term in normalized_title:
            return True
        compact_term = term.replace(" ", "")
        return bool(compact_term and compact_term in compact_title)

    def _build_generic_model_key(self, product_hint: str, normalized: str, match_terms: list[str]) -> str:
        normalized_match_terms = [term.replace(" ", "") for term in match_terms]
        components: list[str] = []
        for token in normalized.split():
            compact_token = token.replace(" ", "")
            if compact_token in normalized_match_terms:
                continue
            if token in GENERIC_MODEL_STOPWORDS:
                continue
            if token.isdigit() and len(token) == 1:
                continue
            if len(token) <= 1:
                continue
            if token not in components:
                components.append(token)
        slug = "-".join(components[:6]) if components else _fallback_hash(normalized)
        return f"{product_hint}-{slug}"
