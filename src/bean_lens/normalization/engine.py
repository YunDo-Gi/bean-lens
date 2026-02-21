"""Normalization engine for extracted bean information."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from bean_lens.schema import BeanInfo
from bean_lens.normalization.repository import Alias, DictionaryRepository, Term
from bean_lens.normalization.types import Domain, Method, NormalizedBeanInfo, NormalizedItem


@dataclass(frozen=True)
class MatchResult:
    key: str
    label_en: str
    label_ko: str
    confidence: float
    method: Method
    candidates: list[str]
    reason: str | None = None


@dataclass(frozen=True)
class NormalizationConfig:
    dictionary_version: str = "v1"
    fuzzy_threshold: float = 0.86
    unknown_queue_path: str | None = None
    unknown_min_confidence: float | None = None


class NormalizationEngine:
    """Dictionary-first normalization engine."""

    def __init__(self, config: NormalizationConfig | None = None):
        self.config = config or NormalizationConfig()
        self.repo = DictionaryRepository(version=self.config.dictionary_version)
        self._term_index = self._build_term_index()

    def normalize_bean_info(self, bean: BeanInfo) -> NormalizedBeanInfo:
        warnings: list[str] = []

        process = self.normalize_one("process", bean.process) if bean.process else None
        if process and process.method == "unmapped":
            warnings.append("process_unmapped")

        roast_level = self.normalize_one("roast_level", bean.roast_level) if bean.roast_level else None
        if roast_level and roast_level.method == "unmapped":
            warnings.append("roast_level_unmapped")

        country_raw = bean.origin.country if bean.origin and bean.origin.country else None
        country = self.normalize_one("country", country_raw) if country_raw else None
        if country and country.method == "unmapped":
            warnings.append("country_unmapped")

        varieties = self._normalize_list("variety", bean.variety or [])
        if any(item.method == "unmapped" for item in varieties):
            warnings.append("variety_partial_unmapped")

        flavor_notes = self._normalize_list("flavor_note", bean.flavor_notes or [])
        if any(item.method == "unmapped" for item in flavor_notes):
            warnings.append("flavor_note_partial_unmapped")

        return NormalizedBeanInfo(
            dictionary_version=self.config.dictionary_version,
            process=process,
            roast_level=roast_level,
            country=country,
            varieties=varieties,
            flavor_notes=flavor_notes,
            warnings=warnings,
        )

    def normalize_one(self, domain: Domain, raw: str | None) -> NormalizedItem:
        if not raw:
            return NormalizedItem(domain=domain, raw="", reason="empty_input")

        value = raw.strip()
        if not value:
            return NormalizedItem(domain=domain, raw=raw, reason="empty_input")

        match = (
            self._match_exact(domain, value)
            or self._match_alias(domain, value)
            or self._match_regex(domain, value)
            or self._match_contains(domain, value)
            or self._match_fuzzy(domain, value)
        )

        if match:
            item = NormalizedItem(
                domain=domain,
                raw=raw,
                normalized_key=match.key,
                normalized_label_en=match.label_en,
                normalized_label_ko=match.label_ko,
                confidence=match.confidence,
                method=match.method,
                candidates=match.candidates,
                reason=match.reason,
            )
            min_conf = self.config.unknown_min_confidence
            if min_conf is not None and item.confidence < min_conf:
                self._enqueue_unknown(
                    domain=domain,
                    raw=raw,
                    confidence=item.confidence,
                    reason="low_confidence",
                    method=item.method,
                    normalized_key=item.normalized_key,
                )
            return item

        self._enqueue_unknown(
            domain=domain,
            raw=raw,
            confidence=0.0,
            reason="no_dictionary_match",
            method="unmapped",
            normalized_key=None,
        )
        return NormalizedItem(
            domain=domain,
            raw=raw,
            confidence=0.0,
            method="unmapped",
            candidates=[],
            reason="no_dictionary_match",
        )

    def _normalize_list(self, domain: Domain, values: list[str]) -> list[NormalizedItem]:
        deduped: list[NormalizedItem] = []
        seen: set[str] = set()

        for raw in values:
            item = self.normalize_one(domain, raw)
            dedupe_key = item.normalized_key or _normalize_text(item.raw)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(item)

        return deduped

    def _build_term_index(self) -> dict[Domain, dict[str, Term]]:
        index: dict[Domain, dict[str, Term]] = {
            "process": {},
            "variety": {},
            "roast_level": {},
            "country": {},
            "flavor_note": {},
        }
        for term in self.repo.terms:
            index[term.domain][term.key] = term
        return index

    def _match_exact(self, domain: Domain, raw: str) -> MatchResult | None:
        normalized_raw = _normalize_text(raw)
        for term in self.repo.terms_by_domain(domain):
            candidates = [term.key, term.label_en, term.label_ko]
            for candidate in candidates:
                if normalized_raw == _normalize_text(candidate):
                    return MatchResult(
                        key=term.key,
                        label_en=term.label_en,
                        label_ko=term.label_ko,
                        confidence=0.98,
                        method="exact",
                        candidates=[term.key],
                    )
        return None

    def _match_alias(self, domain: Domain, raw: str) -> MatchResult | None:
        normalized_raw = _normalize_text(raw)
        aliases = sorted(
            [a for a in self.repo.aliases_by_domain(domain) if a.match_type == "exact"],
            key=lambda item: item.priority,
        )
        for alias in aliases:
            if normalized_raw == _normalize_text(alias.alias):
                return self._match_from_alias(alias, confidence=0.9, method="alias")
        return None

    def _match_regex(self, domain: Domain, raw: str) -> MatchResult | None:
        aliases = sorted(
            [a for a in self.repo.aliases_by_domain(domain) if a.match_type == "regex"],
            key=lambda item: item.priority,
        )
        for alias in aliases:
            if re.search(alias.alias, raw, flags=re.IGNORECASE):
                return self._match_from_alias(alias, confidence=0.88, method="regex")
        return None

    def _match_contains(self, domain: Domain, raw: str) -> MatchResult | None:
        normalized_raw = _normalize_text(raw)
        aliases = sorted(
            [a for a in self.repo.aliases_by_domain(domain) if a.match_type == "contains"],
            key=lambda item: item.priority,
        )
        for alias in aliases:
            if _normalize_text(alias.alias) in normalized_raw:
                return self._match_from_alias(alias, confidence=0.86, method="alias")
        return None

    def _match_fuzzy(self, domain: Domain, raw: str) -> MatchResult | None:
        normalized_raw = _normalize_text(raw)
        best_ratio = 0.0
        best_term: Term | None = None

        for term in self.repo.terms_by_domain(domain):
            for candidate in (term.key, term.label_en, term.label_ko):
                ratio = SequenceMatcher(None, normalized_raw, _normalize_text(candidate)).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_term = term

        if best_term and best_ratio >= self.config.fuzzy_threshold:
            confidence = max(0.7, min(0.85, round(best_ratio, 2)))
            return MatchResult(
                key=best_term.key,
                label_en=best_term.label_en,
                label_ko=best_term.label_ko,
                confidence=confidence,
                method="fuzzy",
                candidates=[best_term.key],
                reason=f"fuzzy_score={best_ratio:.2f}",
            )
        return None

    def _match_from_alias(self, alias: Alias, confidence: float, method: Method) -> MatchResult:
        term = self._term_index[alias.domain][alias.key]
        return MatchResult(
            key=term.key,
            label_en=term.label_en,
            label_ko=term.label_ko,
            confidence=confidence,
            method=method,
            candidates=[term.key],
        )

    def _enqueue_unknown(
        self,
        *,
        domain: Domain,
        raw: str,
        confidence: float,
        reason: str,
        method: Method,
        normalized_key: str | None,
    ) -> None:
        path_value = self.config.unknown_queue_path
        if not path_value:
            return

        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "raw": raw,
            "confidence": confidence,
            "reason": reason,
            "method": method,
            "normalized_key": normalized_key,
            "dictionary_version": self.config.dictionary_version,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_bean_info(
    bean: BeanInfo,
    *,
    dictionary_version: str = "v1",
    fuzzy_threshold: float = 0.86,
    unknown_queue_path: str | None = None,
    unknown_min_confidence: float | None = None,
) -> NormalizedBeanInfo:
    """Normalize extracted BeanInfo using dictionary-based rules."""

    engine = NormalizationEngine(
        config=NormalizationConfig(
            dictionary_version=dictionary_version,
            fuzzy_threshold=fuzzy_threshold,
            unknown_queue_path=unknown_queue_path,
            unknown_min_confidence=unknown_min_confidence,
        )
    )
    return engine.normalize_bean_info(bean)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text
