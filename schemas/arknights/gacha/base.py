"""抽卡记录基础模型"""
from typing import Any
from pydantic import Field, BaseModel, model_validator


class GachaCate(BaseModel):
    id: str
    name: str


class GachaInfo(BaseModel):
    poolId: str
    poolName: str
    charId: str
    charName: str
    rarity: int
    isNew: bool
    gachaTs: str
    pos: int

    @property
    def gacha_ts_sec(self) -> int:
        return int(self.gachaTs) // 1000


class GachaResponse(BaseModel):
    gacha_list: list[GachaInfo] = Field(default=[], alias="list")
    hasMore: bool

    @property
    def next_ts(self) -> str:
        return self.gacha_list[-1].gachaTs if self.gacha_list else ""

    @property
    def next_pos(self) -> int:
        return self.gacha_list[-1].pos if self.gacha_list else 0


class GachaTable(BaseModel):
    gachaPoolId: str
    gachaPoolName: str
    openTime: int
    endTime: int
    gachaRuleType: int


class GachaPull(BaseModel):
    pool_name: str
    char_id: str
    char_name: str
    rarity: int
    is_new: bool
    pos: int


class GachaGroup(BaseModel):
    gacha_ts: int
    pulls: list[GachaPull]

    @model_validator(mode="before")
    @classmethod
    def sort_pulls(cls, values) -> Any:
        if "pulls" in values:
            values["pulls"] = sorted(values["pulls"], key=lambda x: x.pos, reverse=True)
        return values