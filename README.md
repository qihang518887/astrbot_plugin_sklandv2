# AstrBot Plugin - 森空岛V2

基于 [nonebot-plugin-skland](https://github.com/GuGuMur/nonebot-plugin-skland) 移植的 AstrBot 森空岛插件，支持明日方舟和终末地。

保留了原插件的 Jinja2 模板渲染风格，使用 Playwright 生成抽卡分析图片。

## 功能

- **自动签到** — 每日定时签到明日方舟和终末地，支持群内通知
- **抽卡分析** — 明日方舟/终末地抽卡记录可视化，含六星统计、保底计数、UP/歪判定、欧非评分
- **自动导入** — 登录后自动拉取全部抽卡记录
- **扫码登录** — 支持森空岛APP二维码扫码绑定
- **角色查询** — 查看已绑定的游戏角色信息

## 命令一览

| 命令 | 说明 | 备注 |
|------|------|------|
| `/skland` | 显示帮助 | |
| `/sklandlogin <token>` | 登录绑定 | 私聊使用，登录后自动导入抽卡 |
| `/sklandqrcode` | 扫码登录 | 私聊使用 |
| `/sklandlogout` | 登出解绑 | 私聊使用 |
| `/sklandsign` | 手动签到 | 明日方舟 + 终末地 |
| `/sklandstatus` | 查看签到状态 | |
| `/sklandcard` | 查看绑定角色 | |
| `/sklandarkgacha` | 明日方舟抽卡分析 | 渲染图片，含卡池分类/UP判定 |
| `/sklandendgacha` | 终末地抽卡分析 | 渲染图片，含角色池/武器池 |
| `/sklandimport` | 手动导入抽卡记录 | |
| `/sklandgroup` | 群签到订阅 | 开启后自动签到会在群内通知 |
| `/sklandusers` | 用户统计 | 仅管理员 |

## 使用方法

### 1. 获取 Token

1. 浏览器打开 https://web-api.hypergryph.com/account/info/hg
2. 登录鹰角网络通行证
3. 复制页面中 `content` 字段的值（一串字符串）

### 2. 绑定账号

**私聊**机器人发送：

```
/sklandlogin <你的token>
```

绑定成功后会自动导入抽卡记录。

> 也可以使用 `/sklandqrcode` 通过森空岛APP扫码登录。

### 3. 查看抽卡分析

```
/sklandarkgacha    # 明日方舟
/sklandendgacha    # 终末地
```

会返回一张包含卡池统计、保底进度、六星记录的图片。

### 4. 自动签到

插件默认每天凌晨 1:00 自动签到。可通过配置项调整：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_sign_enabled` | `true` | 自动签到开关 |
| `auto_sign_hour` | `1` | 签到时间（0-23） |
| `auto_sign_delay` | `10` | 随机延迟秒数 |
| `show_player_name` | `true` | 显示玩家昵称 |
| `max_users` | `10` | 最大绑定用户数，0为无限 |

### 5. 群签到通知

在群内发送 `/sklandgroup` 可开启/关闭该群的自动签到结果通知。

## 安装

```bash
cd /path/to/astrbot/plugins
git clone https://github.com/qihang518887/astrbot_plugin_sklandv2.git
```

首次使用需安装 Playwright 浏览器：

```bash
playwright install chromium
```

## 依赖

- httpx >= 0.25.0
- pycryptodome >= 3.19.0
- apscheduler >= 3.10.0
- qrcode[pil] >= 7.4.0
- playwright >= 1.40.0
- jinja2 >= 3.1.0
- pydantic >= 2.0.0

## 数据来源

- 卡池元数据（gachaRuleType、开放时间）：[ArknightsGameResource](https://github.com/yuanyan3060/ArknightsGameResource)
- UP角色详情：[PRTS Wiki](https://weedy.prts.wiki/gacha_table.json)
- 抽卡记录：森空岛 Skland API
- 终末地角色头像：[BeyondUID](https://lulush.microgg.cn/BeyondUID)

## 致谢

- [nonebot-plugin-skland](https://github.com/GuGuMur/nonebot-plugin-skland) — 原始实现，本插件的模板和 API 逻辑均移植自此项目
- [AstrBot](https://github.com/Soulter/AstrBot) — 机器人框架

## 许可

MIT License
