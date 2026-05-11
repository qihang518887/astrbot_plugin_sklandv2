"""Jinja2 模板过滤器"""
import json
from urllib.parse import quote
from datetime import datetime
from pathlib import Path


def format_timestamp_md(ms: int) -> str:
    if ms > 1e10:
        return datetime.fromtimestamp(ms / 1000).strftime("%m-%d")
    return datetime.fromtimestamp(ms).strftime("%m-%d")


def charId_to_avatarUrl(charId: str, cache_dir: Path | None = None) -> str:
    avatar_id = next(
        (charId.replace(symbol, "_", 1) for symbol in ["@", "#"] if symbol in charId),
        charId,
    )
    if cache_dir:
        img_path = cache_dir / "avatar" / f"{avatar_id}.png"
        if img_path.exists():
            return img_path.as_uri()
    return f"https://web.hycdn.cn/arknights/game/assets/char/avatar/{charId}.png"


def loads_json(json_str: str) -> dict:
    return json.loads(json_str)


def ef_charId_to_avatarUrl(item_id: str) -> str:
    """终末地角色/武器头像URL拼接"""
    if item_id.startswith("wpn_"):
        return f"https://lulush.microgg.cn/BeyondUID/resource/itemiconbig/{item_id}.png"
    return f"https://lulush.microgg.cn/BeyondUID/resource/charremoteicon/icon_{item_id}.png"