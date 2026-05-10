# AGENTS.md - astrbot_plugin_sklandv2

## 项目概述

**astrbot_plugin_sklandv2** 是一个基于 AstrBot 框架的森空岛插件，从 nonebot-plugin-skland 移植而来，支持：

- **明日方舟（Arknights）**：签到、角色信息卡片、肉鸽战绩
- **终末地（Endfield）**：签到、角色信息

## 目录结构

```
astrbot_plugin_sklandv2/
├── __init__.py          # 插件入口
├── skland_api.py        # API 封装
├── main.py              # 插件主逻辑和命令
└── AGENTS.md            # 本文档
```

## 命令列表

| 命令 | 描述 |
|------|------|
| `/skland` | 显示帮助 |
| `/sklandlogin <token>` | 登录并签到 |
| `/sklandlogout` | 登出 |
| `/sklandsign` | 手动签到 |
| `/sklandstatus` | 查看签到状态 |
| `/sklandcard` | 查询绑定角色 |
| `/sklandrogue <主题>` | 查询肉鸽战绩 |
| `/sklandusers` | 用户统计(仅管理员) |

## 获取 Token

1. 登录 [鹰角网络通行证](https://web-api.hypergryph.com/account/info/hg)
2. 复制 `content` 字段的值
3. 使用 `/sklandlogin <token>` 登录

## 依赖

- `httpx`
- `pycryptodome`

## 开发指南

### 添加新命令

在 `main.py` 中使用 `@filter.command` 装饰器注册新命令：

```python
@filter.command("命令名")
async def handler(self, event: AstrMessageEvent):
    yield event.plain_result("回复内容")
```

### 添加新 API

在 `skland_api.py` 中添加方法，使用已存在的认证流程：

```python
async def get_game_data(self, cred: Credential, uid: str) -> dict:
    did = await self.get_device_id()
    url = f"https://zonai.skland.com/api/v1/game/..."
    headers = self._get_signed_headers(url, "GET", None, cred, did)
    return await self._request("GET", url, headers=headers)
```

## 配置项

- `auto_sign_enabled`: 自动签到开关
- `auto_sign_hour`: 自动签到时间(小时)
- `show_player_name`: 显示玩家名称
- `auto_sign_delay`: 签到随机延时
- `max_users`: 最大用户数