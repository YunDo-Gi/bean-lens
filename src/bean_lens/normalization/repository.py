"""Dictionary repository for normalization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from importlib import import_module

from bean_lens.normalization.types import Domain


@dataclass(frozen=True)
class Term:
    domain: Domain
    key: str
    label_en: str
    label_ko: str


@dataclass(frozen=True)
class Alias:
    domain: Domain
    key: str
    alias: str
    match_type: str
    priority: int
    alias_kind: str = "semantic"


class DictionaryRepository:
    """Loads terms and aliases from packaged dictionary data."""

    def __init__(self, version: str = "v2"):
        self.version = version
        self.terms: list[Term] = self._load_terms()
        self.aliases: list[Alias] = self._load_aliases()

    def terms_by_domain(self, domain: Domain) -> list[Term]:
        return [term for term in self.terms if term.domain == domain]

    def aliases_by_domain(self, domain: Domain) -> list[Alias]:
        return [alias for alias in self.aliases if alias.domain == domain]

    def _load_terms(self) -> list[Term]:
        try:
            module = import_module(f"bean_lens.normalization.data.{self.version}.terms")
            data = module.TERMS
        except ModuleNotFoundError:
            path = files("bean_lens.normalization.data").joinpath(self.version, "terms.json")
            data = json.loads(path.read_text(encoding="utf-8"))
        return [Term(**item) for item in data]

    def _load_aliases(self) -> list[Alias]:
        try:
            module = import_module(f"bean_lens.normalization.data.{self.version}.aliases")
            data = module.ALIASES
        except ModuleNotFoundError:
            path = files("bean_lens.normalization.data").joinpath(self.version, "aliases.json")
            data = json.loads(path.read_text(encoding="utf-8"))
        return [Alias(**item) for item in data]
