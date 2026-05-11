"""游戏数据加载与管理"""
import logging
import httpx
from .exception import RequestException

logger = logging.getLogger("skland_data_source")

PRTS_GACHA_TABLE_URL = "https://weedy.prts.wiki/gacha_table.json"

# GitHub 镜像列表（按优先级排序，国内环境 raw.githubusercontent.com 经常超时）
GITHUB_GACHA_TABLE_URLS = [
    "https://raw.gitmirror.com/yuanyan3060/ArknightsGameResource/main/gamedata/excel/gacha_table.json",
    "https://cdn.jsdelivr.net/gh/yuanyan3060/ArknightsGameResource@main/gamedata/excel/gacha_table.json",
    "https://raw.githubusercontent.com/yuanyan3060/ArknightsGameResource/main/gamedata/excel/gacha_table.json",
]


class GachaTableData:
    """明日方舟卡池数据管理

    数据来源：
    - GitHub ArknightsGameResource: 卡池元数据 (gachaRuleType, openTime, endTime)
    - PRTS Wiki: UP角色详情 (gachaPoolDetail.detailInfo.upCharInfo/availCharInfo)
    """

    def __init__(self) -> None:
        self.gacha_table: list[dict] = []
        self.gacha_details: list[dict] = []
        self._loaded: bool = False

    async def load(self) -> bool:
        """从 GitHub + PRTS Wiki 下载并解析卡池数据"""
        if self._loaded and self.gacha_table:
            return True
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # 1. 从 GitHub 获取卡池元数据 (gachaRuleType, openTime, endTime)
                gh_success = False
                for url in GITHUB_GACHA_TABLE_URLS:
                    try:
                        resp_gh = await client.get(url)
                        resp_gh.raise_for_status()
                        gh_data = resp_gh.json()
                        gh_pools = gh_data.get("gachaPoolClient", [])
                        self.gacha_table = []
                        for item in gh_pools:
                            self.gacha_table.append({
                                "gachaPoolId": item.get("gachaPoolId", ""),
                                "gachaPoolName": item.get("gachaPoolName", ""),
                                "openTime": item.get("openTime", 0),
                                "endTime": item.get("endTime", 0),
                                "gachaRuleType": item.get("gachaRuleType", 0),
                            })
                        logger.info(f"GitHub 卡池元数据加载成功: {len(self.gacha_table)} 个卡池 (from {url[:40]}...)")
                        gh_success = True
                        break
                    except Exception as e:
                        logger.debug(f"GitHub 镜像 {url[:50]} 失败: {e}")
                        continue

                if not gh_success:
                    logger.warning("所有 GitHub 镜像均获取失败，卡池分类将不可用")
                    self.gacha_table = []

                # 2. 从 PRTS Wiki 获取 UP 角色详情
                try:
                    resp_prts = await client.get(PRTS_GACHA_TABLE_URL)
                    resp_prts.raise_for_status()
                    prts_data = resp_prts.json()
                    prts_pools = prts_data.get("gachaPoolClient", [])
                    self.gacha_details = []
                    for item in prts_pools:
                        if "gachaPoolDetail" in item and item["gachaPoolDetail"]:
                            self.gacha_details.append({
                                "gachaPoolId": item.get("gachaPoolId", ""),
                                "gachaPoolDetail": item.get("gachaPoolDetail", {}),
                            })
                    logger.info(f"PRTS UP角色详情加载成功: {len(self.gacha_details)} 个卡池")
                except Exception as e:
                    logger.warning(f"PRTS UP角色详情获取失败: {e}")
                    self.gacha_details = []

                self._loaded = bool(self.gacha_table or self.gacha_details)
                return self._loaded
        except Exception as e:
            logger.warning(f"卡池数据加载失败: {e}")
            return False

    def invalidate(self):
        """强制下次重新加载"""
        self._loaded = False
        self.gacha_table = []
        self.gacha_details = []
