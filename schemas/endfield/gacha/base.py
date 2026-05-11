"""终末地抽卡记录基础模型"""
from typing import Any
from pydantic import BaseModel, model_validator


class EfGachaPoolType:
    """终末地卡池类型常量"""
    STANDARD = "standard"
    SPECIAL = "special"
    BEGINNER = "beginner"
    WEAPON = "weapon"


class EfGachaPull(BaseModel):
    """终末地单次抽卡记录"""
    pool_name: str
    item_id: str
    item_name: str
    item_type: str = "char"
    rarity: int
    is_new: bool
    is_free: bool = False
    seq_id: int


class EfGachaGroup(BaseModel):
    """终末地同一时间戳下的一组抽卡记录"""
    gacha_ts: int
    pulls: list[EfGachaPull]

    @model_validator(mode="before")
    @classmethod
    def sort_pulls(cls, values) -> Any:
        if "pulls" in values:
            pulls = values["pulls"]
            if pulls and isinstance(pulls[0], dict):
                values["pulls"] = sorted(pulls, key=lambda x: x["seq_id"], reverse=True)
            else:
                values["pulls"] = sorted(pulls, key=lambda x: x.seq_id, reverse=True)
        return values
