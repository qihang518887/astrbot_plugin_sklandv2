"""抽卡记录分组和卡池数据查询"""
from collections import defaultdict
from pathlib import Path
from .schemas.arknights.gacha.base import GachaPull, GachaGroup
from .schemas.arknights.gacha.pool import GachaPool
from .schemas.arknights.gacha.statistics import GroupedGachaRecord
from .data_source import GachaTableData


class GachaRecordItem:
    """本地抽卡记录数据类 (替代 ORM model)"""
    def __init__(self, pool_id: str = "", pool_name: str = "", char_id: str = "",
                 char_name: str = "", rarity: int = 0, is_new: bool = False,
                 gacha_ts: int = 0, pos: int = 0, app_code: str = "arknights"):
        self.pool_id = pool_id
        self.pool_name = pool_name
        self.char_id = char_id
        self.char_name = char_name
        self.rarity = rarity
        self.is_new = is_new
        self.gacha_ts = gacha_ts
        self.pos = pos
        self.app_code = app_code


def group_gacha_records(records: list[GachaRecordItem], gacha_data: GachaTableData | None = None) -> GroupedGachaRecord:
    """将抽卡记录按卡池分组"""
    temp_grouped_records = defaultdict(lambda: defaultdict(list))
    for record in records:
        temp_grouped_records[record.pool_id][record.gacha_ts].append(record)

    final_pools_data: list[GachaPool] = []
    for pool_id, ts_dict in temp_grouped_records.items():
        up_five_chars, up_six_chars = _get_up_chars(pool_id, gacha_data)
        open_time, end_time, gacha_rule_type = _get_pool_info(pool_id, gacha_data)
        gacha_groups: list[GachaGroup] = [
            GachaGroup(
                gacha_ts=gacha_ts,
                pulls=[
                    GachaPull(
                        pool_name=p.pool_name,
                        char_id=p.char_id,
                        char_name=p.char_name,
                        rarity=p.rarity,
                        is_new=p.is_new,
                        pos=p.pos,
                    )
                    for p in pulls
                ],
            )
            for gacha_ts, pulls in ts_dict.items()
        ]
        first_pool_name = gacha_groups[0].pulls[0].pool_name if gacha_groups else ""
        gacha_pool = GachaPool(
            gachaPoolId=pool_id,
            gachaPoolName=first_pool_name,
            openTime=open_time,
            endTime=end_time,
            up_five_chars=up_five_chars,
            up_six_chars=up_six_chars,
            gachaRuleType=gacha_rule_type,
            records=gacha_groups,
        )
        final_pools_data.append(gacha_pool)
    return GroupedGachaRecord(pools=final_pools_data)


def _get_up_chars(pool_id: str, gacha_data: GachaTableData | None):
    up_five_chars, up_six_chars = [], []
    if not gacha_data:
        return up_five_chars, up_six_chars
    for gacha_detail in gacha_data.gacha_details:
        if gacha_detail.get("gachaPoolId") != pool_id:
            continue
        detail = gacha_detail.get("gachaPoolDetail", {}).get("detailInfo", {})
        up_char = detail.get("upCharInfo")
        avail_char = detail.get("availCharInfo")
        # 优先从 upCharInfo 获取 UP 角色
        if up_char and up_char.get("perCharList"):
            for item in up_char.get("perCharList", []):
                if item.get("rarityRank") == 4:
                    up_five_chars = item.get("charIdList", [])
                elif item.get("rarityRank") == 5:
                    up_six_chars = item.get("charIdList", [])
        # 仅当 upCharInfo 没有六星UP时，才从 availCharInfo 取（常驻池等）
        if not up_six_chars and avail_char and avail_char.get("perAvailList"):
            for item in avail_char.get("perAvailList", []):
                if item.get("rarityRank") == 4 and not up_five_chars:
                    up_five_chars = item.get("charIdList", [])
                elif item.get("rarityRank") == 5:
                    up_six_chars = item.get("charIdList", [])
    return up_five_chars, up_six_chars


def _get_pool_info(pool_id: str, gacha_data: GachaTableData | None):
    if not gacha_data:
        return 0, 0, 0
    for gacha_table in gacha_data.gacha_table:
        if gacha_table.get("gachaPoolId") == pool_id:
            return gacha_table.get("openTime", 0), gacha_table.get("endTime", 0), gacha_table.get("gachaRuleType", 0)
    return 0, 0, 0