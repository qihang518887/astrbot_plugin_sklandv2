"""游戏数据加载与管理"""
import json
import logging
from pathlib import Path

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

# 终末地卡池数据镜像（FrostN0v0/EndfieldGachaPoolTable）
EF_GACHA_POOL_TABLE_URLS = [
    "https://raw.gitmirror.com/FrostN0v0/EndfieldGachaPoolTable/master/GachaPoolTable.json",
    "https://cdn.jsdelivr.net/gh/FrostN0v0/EndfieldGachaPoolTable@master/GachaPoolTable.json",
    "https://raw.githubusercontent.com/FrostN0v0/EndfieldGachaPoolTable/master/GachaPoolTable.json",
]

# 缓存目录（与插件同目录）
_PLUGIN_DIR = Path(__file__).resolve().parent
_CACHE_DIR = _PLUGIN_DIR / ".cache"
EF_POOL_CACHE_FILE = _CACHE_DIR / "ef_gacha_pool_table.json"


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


class EfGachaPoolTableData:
    """终末地卡池数据管理

    从 GitHub 仓库 FrostN0v0/EndfieldGachaPoolTable 拉取 GachaPoolTable.json，
    解析为 dict[str, EfGachaContentPool]，提供按 pool_id 查询卡池 UP 信息的能力。
    每次调用 load() 都尝试拉取最新数据，失败时使用本地缓存。
    """

    def __init__(self) -> None:
        self.pool_table: dict = {}
        self._loaded: bool = False

    async def load(self, force: bool = False) -> bool:
        """下载并加载终末地卡池数据

        Args:
            force: 即使已加载也强制重新拉取

        Returns:
            是否成功加载（包括从缓存恢复）
        """
        if self._loaded and self.pool_table and not force:
            return True

        # 尝试从镜像下载最新数据
        downloaded = False
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for url in EF_GACHA_POOL_TABLE_URLS:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    raw = resp.json()
                    if not isinstance(raw, dict) or not raw:
                        continue
                    self._parse(raw)
                    self._save_cache(resp.content)
                    logger.info(
                        f"终末地卡池数据下载成功: {len(self.pool_table)} 个卡池 (from {url[:40]}...)"
                    )
                    downloaded = True
                    break
                except Exception as e:
                    logger.debug(f"终末地卡池镜像 {url[:50]} 失败: {e}")
                    continue

        # 下载失败时回退到本地缓存
        if not downloaded:
            if EF_POOL_CACHE_FILE.exists():
                try:
                    raw = json.loads(EF_POOL_CACHE_FILE.read_text(encoding="utf-8"))
                    self._parse(raw)
                    logger.warning(
                        f"终末地卡池数据下载失败，使用本地缓存: {len(self.pool_table)} 个卡池"
                    )
                except Exception as e:
                    logger.warning(f"终末地卡池缓存加载失败: {e}")
                    return False
            else:
                logger.warning("所有终末地卡池镜像均获取失败，且无本地缓存")
                return False

        self._loaded = bool(self.pool_table)
        return self._loaded

    def _parse(self, raw: dict) -> None:
        """解析 GachaPoolTable.json 为 dict[str, EfGachaContentPool]"""
        from .schemas.endfield.gacha.base import EfGachaContentPool

        pools = {}
        for pool_id, data in raw.items():
            if not isinstance(data, dict):
                continue
            try:
                pools[pool_id] = EfGachaContentPool(**data)
            except Exception as e:
                logger.debug(f"解析卡池 {pool_id} 失败: {e}")
                continue
        self.pool_table = pools

    def _save_cache(self, content: bytes) -> None:
        """保存原始 JSON 到缓存文件"""
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            EF_POOL_CACHE_FILE.write_bytes(content)
        except Exception as e:
            logger.debug(f"终末地卡池缓存保存失败: {e}")

    def get_pool(self, pool_id: str):
        """按 pool_id 查询卡池信息"""
        return self.pool_table.get(pool_id)

    def invalidate(self):
        """强制下次重新加载"""
        self._loaded = False
        self.pool_table = {}


# 全局单例
ef_gacha_pool_data = EfGachaPoolTableData()
