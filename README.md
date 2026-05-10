# AstrBot Plugin - 森空岛V2

森空岛签到和数据查询插件，支持明日方舟和终末地。

## 功能

- **自动签到**: 每日定时签到，支持明日方舟和终末地
- **自动导入抽卡记录**: 登录后自动导入明日方舟和终末地抽卡记录
- **角色卡片**: 查询绑定角色信息
- **抽卡记录**: 查询明日方舟和终末地抽卡记录
- **扫码登录**: 支持二维码扫码登录
- **群签到统计**: 群内查看签到状态

## 命令

| 命令 | 描述 |
|------|------|
| `/skland help` | 显示帮助 |
| `/skland login <token>` | 登录并自动导入抽卡(私聊) |
| `/skland qrcode` | 扫码登录 |
| `/skland logout` | 登出(私聊) |
| `/skland sign` | 手动签到 |
| `/skland status` | 签到状态 |
| `/skland card` | 绑定角色 |
| `/skland ark chouka` | 明日方舟抽卡 |
| `/skland end chouka` | 终末地抽卡 |
| `/skland import <url>` | 导入抽卡 |
| `/skland group` | 群签到订阅 |
| `/skland users` | 用户统计(仅管理员) |

## 获取 Token

1. 打开 https://web-api.hypergryph.com/account/info/hg
2. 复制 `content` 字段的值
3. 使用 `/skland login <token>` 登录

## 安装

```bash
cd /path/to/astrbot/plugins
git clone https://github.com/Azincc/astrbot_plugin_sklandv2.git
```

## 依赖

- httpx>=0.25.0
- pycryptodome>=3.19.0
- apscheduler>=3.10.0
- qrcode[pil]>=7.4.0
- playwright>=1.40.0

## 许可

MIT License