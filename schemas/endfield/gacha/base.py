"""终末地抽卡记录基础模型"""
from typing import Any
from pydantic import BaseModel, Field, model_validator


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


class EfGachaContentChar(BaseModel):
    """卡池角色/武器条目（GachaPoolTable 与 Content API 共用）"""
    id: str = ""
    name: str = ""
    rarity: int = 0
    """稀有度（1-indexed: 6=6★, 5=5★, 4=4★）"""

    model_config = {"extra": "ignore"}


class EfGachaContentRotateItem(BaseModel):
    """轮换UP角色信息"""
    name: str = ""
    times: int = 0

    model_config = {"extra": "ignore"}


class EfGachaContentPool(BaseModel):
    """终末地卡池详细信息

    数据来源：
    - 本地 GachaPoolTable.json (FrostN0v0/EndfieldGachaPoolTable 仓库)
    - 实时 Content API (zonai.skland.com/.../gacha/content)
    """
    pool_gacha_type: str = ""
    """卡池物品类型: 'char' 或 'weapon'"""
    pool_name: str = ""
    pool_type: str = ""
    """卡池分类: 'special' / 'standard' / 'beginner' / 'weapon' (仅 GachaPoolTable 有)"""
    up6_name: str = ""
    up6_image: str = ""
    """UP六星横幅图片URL"""
    up5_name: str = ""
    up5_image: str = ""
    rotate_image: str = ""
    """轮换UP横幅图片URL（fallback 用）"""
    all: list[EfGachaContentChar] = Field(default_factory=list)
    rotate_list: list[EfGachaContentRotateItem] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def normalize_nulls(cls, values) -> Any:
        """将 JSON 中的 null 转为对应类型的默认值"""
        if isinstance(values, dict):
            for key in (
                "pool_gacha_type", "pool_name", "pool_type",
                "up6_name", "up6_image", "up5_name", "up5_image", "rotate_image",
            ):
                if values.get(key) is None:
                    values[key] = ""
            for key in ("all", "rotate_list"):
                if values.get(key) is None:
                    values[key] = []
        return values

    @property
    def up_six_char_ids(self) -> list[str]:
        """UP六星角色/武器的ID列表

        仅返回 up6_name 对应的条目（当期真正的UP），
        rotate_list 中的其他轮换角色不算UP（抽到算歪）。
        """
        if self.up6_name:
            return [c.id for c in self.all if c.rarity == 6 and c.name == self.up6_name]
        return []

    @property
    def category(self) -> str:
        """卡池分类（normalized）"""
        if self.pool_type:
            pt = self.pool_type.lower()
            if pt in ("special", "standard", "beginner", "weapon"):
                return pt
        # fallback：根据 pool_gacha_type 推断
        if self.pool_gacha_type == "weapon":
            return "weapon"
        return "standard"


class EfGachaContentResponse(BaseModel):
    """Content API 响应（单个卡池的UP角色信息）"""
    pool: EfGachaContentPool
    timezone: int = 8

    model_config = {"extra": "ignore"}
