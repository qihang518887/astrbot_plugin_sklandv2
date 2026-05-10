"""游戏数据加载与管理"""
import json
from pathlib import Path
from typing import TYPE_CHECKING
import httpx
from .exception import RequestException

if TYPE_CHECKING:
    from .schemas.arknights.gacha.base import GachaTable, GachaDetails


class GachaTableData:
    """明日方舟卡池数据管理"""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.gacha_data_path = data_dir / "gamedata" / "excel"
        self.gacha_table: list = []
        self.gacha_details: list = []

    async def get_gacha_details(self):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get("https://weedy.prts.wiki/gacha_table.json")
                response.raise_for_status()
                data = response.json()["gachaPoolClient"]
                self.gacha_details = [dict(**item) for item in data]
        except httpx.HTTPError as e:
            raise RequestException(f"获取卡池详情失败: {type(e).__name__}: {e}")

    async def load(self) -> bool:
        gacha_path = self.gacha_data_path / "gacha_table.json"
        if not gacha_path.exists():
            return False
        try:
            gacha_json = json.loads(gacha_path.read_text(encoding="utf-8"))
            self.gacha_table = gacha_json.get("gachaPoolClient", [])
            await self.get_gacha_details()
        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
            raise RequestException(f"加载卡池数据失败: {e}")
        return True