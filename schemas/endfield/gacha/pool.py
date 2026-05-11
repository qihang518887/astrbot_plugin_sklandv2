"""终末地卡池相关模型"""
from typing import Any
from pydantic import BaseModel, model_validator
from .base import EfGachaPull, EfGachaGroup

# 角色池武库配额产出规则
ARSENAL_QUOTA_EARN_MAP: dict[int, int] = {
    4: 20,
    5: 200,
    6: 2000,
}

WEAPON_TEN_PULL_COST: int = 1980


class EfGachaPoolInfo(BaseModel):
    """终末地卡池信息"""
    pool_id: str
    pool_name: str
    pool_type: str = "char"
    records: list[EfGachaGroup]
    up_six_chars: list[str] = []
    up6_img: str = ""
    up6_name: str = ""

    @property
    def pool_category(self) -> str:
        pid = self.pool_id.lower()
        if pid.startswith("special"):
            return "special"
        if pid.startswith("weapon") or pid.startswith("wepon"):
            return "weapon"
        if pid == "beginner":
            return "beginner"
        return "standard"

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
    def all_pulls_reverse_chronological(self) -> list[EfGachaPull]:
        pulls: list[EfGachaPull] = []
        for record in self.records:
            for pull in record.pulls:
                pulls.append(pull)
        return pulls

    @property
    def total_pulls(self) -> int:
        return sum(len(record.pulls) for record in self.records)

    @property
    def paid_pulls(self) -> int:
        return sum(1 for record in self.records for pull in record.pulls if not pull.is_free)

    @property
    def free_pulls(self) -> int:
        return sum(1 for record in self.records for pull in record.pulls if pull.is_free)

    @property
    def total_six_stars(self) -> int:
        return sum(1 for record in self.records for pull in record.pulls if pull.rarity == 6)

    @property
    def total_six_spook(self) -> int:
        return sum(
            1 for record in self.records for pull in record.pulls
            if pull.rarity == 6 and pull.item_id not in self.up_six_chars
        )

    @property
    def arsenal_quota_earned(self) -> int:
        return sum(ARSENAL_QUOTA_EARN_MAP.get(pull.rarity, 0) for record in self.records for pull in record.pulls)

    @property
    def ten_pull_count(self) -> int:
        ten_pulls: set[tuple[int, int]] = set()
        for group in self.records:
            paid = [p for p in group.pulls if not p.is_free]
            if not paid:
                continue
            sorted_paid = sorted(paid, key=lambda p: p.seq_id)
            current_start = sorted_paid[0].seq_id
            prev_seq = current_start
            for p in sorted_paid[1:]:
                if p.seq_id != prev_seq + 1:
                    ten_pulls.add((group.gacha_ts, current_start))
                    current_start = p.seq_id
                prev_seq = p.seq_id
            ten_pulls.add((group.gacha_ts, current_start))
        return len(ten_pulls)

    @property
    def arsenal_quota_consumed(self) -> int:
        return self.ten_pull_count * WEAPON_TEN_PULL_COST

    @property
    def pity_count(self) -> int:
        """当前已垫抽数（排除 isFree）"""
        count = 0
        for pull in self.all_pulls_reverse_chronological:
            if pull.is_free:
                continue
            if pull.rarity == 6:
                return count
            count += 1
        return count

    @property
    def up_pity_count(self) -> int:
        count = 0
        for pull in self.all_pulls_reverse_chronological:
            if pull.is_free:
                continue
            if pull.rarity == 6 and pull.item_id in self.up_six_chars:
                return count
            count += 1
        return count
