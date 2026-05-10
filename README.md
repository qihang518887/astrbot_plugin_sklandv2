# AstrBot Plugin - 森空岛V2

森空岛签到和数据查询插件，支持明日方舟和终末地。

## 功能

- **自动签到**: 每日定时签到，支持明日方舟和终末地
- **自动导入抽卡记录**: 登录后自动导入明日方舟和终末地抽卡记录
- **角色卡片**: 查询绑定角色信息
- **抽卡分析**: 查询明日方舟和终末地抽卡记录，含六星统计、保底计数
- **扫码登录**: 支持森空岛APP二维码扫码登录
- **群签到订阅**: 群内自动签到通知

## 命令

| 命令 | 描述 |
|------|------|
| `/skland` | 显示帮助 |
| `/sklandlogin <token>` | 登录并自动导入抽卡(私聊) |
| `/sklandqrcode` | 扫码登录 |
| `/sklandlogout` | 登出(私聊) |
| `/sklandsign` | 手动签到 |
| `/sklandstatus` | 签到状态 |
| `/sklandcard` | 绑定角色 |
| `/sklandarkgacha` | 明日方舟抽卡分析 |
| `/sklandendgacha` | 终末地抽卡分析 |
| `/sklandimport` | 自动导入抽卡记录 |
| `/sklandgroup` | 群签到订阅 |
| `/sklandusers` | 用户统计(仅管理员) |

## 获取 Token

1. 打开 https://web-api.hypergryph.com/account/info/hg
2. 复制 `content` 字段的值
3. 使用 `/sklandlogin <token>` 登录

## 安装

```bash
cd /path/to/astrbot/plugins
git clone https://github.com/qihang518887/astrbot_plugin_sklandv2.git
```

## 依赖

- httpx>=0.25.0
- pycryptodome>=3.19.0
- apscheduler>=3.10.0
- qrcode[pil]>=7.4.0
- playwright>=1.40.0
- jinja2>=3.1.0

## 许可

MIT License