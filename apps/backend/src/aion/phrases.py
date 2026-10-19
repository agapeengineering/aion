"""Shared source-controlled content. Only explicitly cleared weekly entries can ship."""

import json
from datetime import date
from functools import lru_cache
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class Translation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    translator: str
    source: str
    rights: str
    approved: StrictBool


class Phrase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    author: str
    work: str
    location: str
    original_language: str = Field(min_length=1, max_length=35)
    original: str
    source_url: str = Field(pattern=r"^https://[^\s]+$", max_length=2048)
    rights: str
    approved: StrictBool
    en: Translation
    es: Translation


class Collection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=1, le=1)
    collectionVersion: str = Field(min_length=1, max_length=64)
    anchorSunday: date
    sequence: list[str]
    phrases: list[Phrase]

    @model_validator(mode="after")
    def valid(self) -> Collection:
        ids = [p.id for p in self.phrases]
        if self.version != 1 or self.anchorSunday != date(2026, 10, 18):
            raise ValueError("Unsupported weekly collection")
        if len(set(ids)) != len(ids) or len(set(self.sequence)) != len(self.sequence):
            raise ValueError("Duplicate phrase ID")
        index = {p.id: p for p in self.phrases}
        for key in self.sequence:
            p = index.get(key)
            if not p or not (p.approved and p.en.approved and p.es.approved):
                raise ValueError("Sequence requires approved original and both translations")
            if not all(
                value.strip()
                for value in (
                    p.author,
                    p.work,
                    p.location,
                    p.original,
                    p.source_url,
                    p.rights,
                    p.en.text,
                    p.en.translator,
                    p.en.source,
                    p.en.rights,
                    p.es.text,
                    p.es.translator,
                    p.es.source,
                    p.es.rights,
                )
            ):
                raise ValueError("Incomplete phrase attribution or rights")
        return self

    def for_date(self, day: date) -> Phrase | None:
        week = (day - self.anchorSunday).days // 7
        if week < 0 or week >= len(self.sequence):
            return None  # Never cycle silently, skip entries, or substitute an unapproved passage.
        key = self.sequence[week]
        return next(p for p in self.phrases if p.id == key)


@lru_cache
def weekly_collection() -> Collection:
    return Collection.model_validate_json(
        files("aion").joinpath("content/weekly-phrases.json").read_text()
    )


@lru_cache
def original_phrases() -> list[dict[str, str]]:
    data = json.loads(files("aion").joinpath("content/original-phrases.json").read_text())
    return list(data["phrases"])
