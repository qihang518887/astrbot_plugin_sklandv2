"""终末地抽卡统计模型"""
from typing import Any
from pydantic import BaseModel, model_validator
from .base import EfGachaPull
from .pool import EfGachaPoolInfo


class EfGroupedGachaRecord(BaseModel):
    """终末地分组后的抽卡记录"""
    beginner_pools: list[EfGachaPoolInfo] = []
    standard_pools: list[EfGachaPoolInfo] = []
    special_pools: list[EfGachaPoolInfo] = []
    weapon_pools: list[EfGachaPoolInfo] = []

    @model_validator(mode="before")
    @classmethod
    def sort_pools(cls, values) -> Any:
        if isinstance(values, dict):
            for key in ("beginner_pools", "standard_pools", "special_pools", "weapon_pools"):
                if key in values and values[key]:
                    values[key] = sorted(
                        values[key],
                        key=lambda x: max((r.gacha_ts for r in x.records), default=0),
                        reverse=True,
                    )
        return values

    @property
    def char_pools(self) -> list[EfGachaPoolInfo]:
        return self.beginner_pools + self.standard_pools + self.special_pools

    @property
    def all_pools(self) -> list[EfGachaPoolInfo]:
        return self.char_pools + self.weapon_pools

    @property
    def flat_pools(self) -> list[EfGachaPoolInfo]:
        return sorted(
            self.all_pools,
            key=lambda p: max((r.gacha_ts for r in p.records), default=0),
            reverse=True,
        )

    def get_visible_pool_ids(self, begin: int | None = None, limit: int | None = None) -> set[str]:
        visible: set[str] = set()
        for pools in (self.special_pools, self.weapon_pools, self.standard_pools, self.beginner_pools):
            for p in pools[begin:limit]:
                visible.add(p.pool_id)
        return visible

    # ── 抽数统计 ──

    @property
    def beginner_total_pulls(self) -> int:
        return sum(pool.total_pulls for pool in self.beginner_pools)

    @property
    def standard_total_pulls(self) -> int:
        return sum(pool.total_pulls for pool in self.standard_pools)

    @property
    def standard_total_six(self) -> int:
        return sum(pool.total_six_stars for pool in self.standard_pools)

    @property
    def standard_six_avg(self) -> float:
        six_count = self.standard_total_six
        if six_count == 0:
            return 0.0
        total_paid = sum(pool.paid_pulls for pool in self.standard_pools)
        return (total_paid - self.standard_pity) / six_count

    @property
    def special_total_pulls(self) -> int:
        return sum(pool.total_pulls for pool in self.special_pools)

    @property
    def special_total_six(self) -> int:
        return sum(pool.total_six_stars for pool in self.special_pools)

    @property
    def special_total_spook(self) -> int:
        return sum(pool.total_six_spook for pool in self.special_pools)

    @property
    def special_up_count(self) -> int:
        return self.special_total_six - self.special_total_spook

    @property
    def special_up_avg(self) -> float:
        up_count = self.special_up_count
        if up_count == 0:
            return 0.0
        total_paid = sum(pool.paid_pulls for pool in self.special_pools)
        pity_after_last_up = self._special_up_pity()
        return (total_paid - pity_after_last_up) / up_count

    @property
    def char_total_pulls(self) -> int:
        return self.beginner_total_pulls + self.standard_total_pulls + self.special_total_pulls

    @property
    def weapon_total_pulls(self) -> int:
        return sum(pool.total_pulls for pool in self.weapon_pools)

    @property
    def total_pulls(self) -> int:
        return self.char_total_pulls + self.weapon_total_pulls

    # ── 武库配额 ──

    @property
    def char_arsenal_quota_earned(self) -> int:
        return sum(pool.arsenal_quota_earned for pool in self.char_pools)

    @property
    def weapon_arsenal_quota_consumed(self) -> int:
        return sum(pool.arsenal_quota_consumed for pool in self.weapon_pools)

    @property
    def arsenal_quota_net(self) -> int:
        return self.char_arsenal_quota_earned - self.weapon_arsenal_quota_consumed

    # ── STANDARD 保底 ──

    @property
    def standard_pity(self) -> int:
        if not self.standard_pools:
            return 0
        latest_pool = max(
            self.standard_pools,
            key=lambda p: max((r.gacha_ts for r in p.records), default=0),
            default=None,
        )
        return latest_pool.pity_count if latest_pool else 0

    # ── SPECIAL 保底（跨池继承） ──

    def _special_all_pulls_chronological(self) -> list[tuple[EfGachaPull, str]]:
        all_entries: list[tuple[int, int, EfGachaPull, str]] = []
        for pool in self.special_pools:
            for group in pool.records:
                for pull in group.pulls:
                    all_entries.append((group.gacha_ts, pull.seq_id, pull, pool.pool_id))
        all_entries.sort(key=lambda x: (x[0], x[1]))
        return [(entry[2], entry[3]) for entry in all_entries]

    @property
    def special_pity(self) -> int:
        all_pulls = self._special_all_pulls_chronological()
        count = 0
        for pull, _ in reversed(all_pulls):
            if pull.is_free:
                continue
            if pull.rarity == 6:
                return count
            count += 1
        return count

    def _special_up_pity(self) -> int:
        all_pulls = self._special_all_pulls_chronological()
        count = 0
        for pull, pool_id in reversed(all_pulls):
            if pull.is_free:
                continue
            pool_obj = next((p for p in self.special_pools if p.pool_id == pool_id), None)
            if pool_obj and pull.rarity == 6 and pull.item_id in pool_obj.up_six_chars:
                return count
            count += 1
        return count

    # ── 武器池 ──

    @property
    def weapon_total_six(self) -> int:
        return sum(pool.total_six_stars for pool in self.weapon_pools)

    @property
    def weapon_total_spook(self) -> int:
        return sum(pool.total_six_spook for pool in self.weapon_pools)

    @property
    def weapon_up_count(self) -> int:
        return self.weapon_total_six - self.weapon_total_spook

    @property
    def weapon_up_avg(self) -> float:
        up_count = self.weapon_up_count
        if up_count == 0:
            return 0.0
        total_paid = sum(pool.paid_pulls for pool in self.weapon_pools)
        pity_after_last_up = self._weapon_up_pity()
        return (total_paid - pity_after_last_up) / up_count

    def _weapon_up_pity(self) -> int:
        all_entries: list[tuple[int, int, EfGachaPull, str]] = []
        for pool in self.weapon_pools:
            for group in pool.records:
                for pull in group.pulls:
                    all_entries.append((group.gacha_ts, pull.seq_id, pull, pool.pool_id))
        all_entries.sort(key=lambda x: (x[0], x[1]))
        count = 0
        for _, _, pull, pool_id in reversed(all_entries):
            if pull.is_free:
                continue
            pool_obj = next((p for p in self.weapon_pools if p.pool_id == pool_id), None)
            if pool_obj and pull.rarity == 6 and pull.item_id in pool_obj.up_six_chars:
                return count
            count += 1
        return count

    @property
    def weapon_pity(self) -> int:
        if not self.weapon_pools:
            return 0
        latest_pool = max(
            self.weapon_pools,
            key=lambda p: max((r.gacha_ts for r in p.records), default=0),
            default=None,
        )
        return latest_pool.pity_count if latest_pool else 0
