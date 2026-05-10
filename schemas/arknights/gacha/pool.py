"""卡池相关模型"""
from typing import Any
from pydantic import model_validator
from .base import GachaGroup, GachaTable


class GachaPool(GachaTable):
    up_five_chars: list[str]
    up_six_chars: list[str]
    records: list[GachaGroup]

    @model_validator(mode="before")
    @classmethod
    def sort_records(cls, values) -> Any:
        if "records" in values:
            records = values["records"]
            if records and isinstance(records[0], dict):
                values["records"] = sorted(records, key=lambda x: x["gacha_ts"], reverse=True)
            else:
                values["records"] = sorted(records, key=lambda x: x.gacha_ts, reverse=True)
        return values

    @property
    def total_pulls(self) -> int:
        return sum(len(record.pulls) for record in self.records)

    @property
    def total_six_spook(self) -> int:
        return sum(
            1
            for record in self.records
            for pull in record.pulls
            if pull.rarity == 5 and pull.char_id not in self.up_six_chars
        )

    @property
    def total_six_stars(self) -> int:
        return sum(1 for record in self.records for pull in record.pulls if pull.rarity == 5)

    @property
    def bare_six_consume(self) -> int:
        all_pulls_chronological = []
        for record in reversed(self.records):
            all_pulls_chronological.extend(reversed(record.pulls))
        last_six_star_index = next(
            (i for i in range(len(all_pulls_chronological) - 1, -1, -1) if all_pulls_chronological[i].rarity == 5),
            -1,
        )
        return last_six_star_index + 1