# AstrBot Plugin - 森空岛V2

森空岛签到和数据查询插件，支持明日方舟和终末地。

## 功能

- **自动签到**: 每日定时签到，支持明日方舟和终末地
- **角色卡片**: 查询绑定角色信息
- **肉鸽战绩**: 查询明日方舟肉鸽战绩

## 命令

| 命令 | 描述 |
|------|------|
| `/skland` | 显示帮助 |
| `/sklandlogin <token>` | 登录并签到(私聊) |
| `/sklandlogout` | 登出(私聊) |
| `/sklandsign` | 手动签到 |
| `/sklandstatus` | 查看签到状态 |
| `/sklandcard` | 查询绑定角色 |
| `/sklandrogue <主题>` | 查询肉鸽战绩 |
| `/sklandusers` | 用户统计(仅管理员) |

## 获取 Token

1. 登录 [鹰角网络通行证](https://web-api.hypergryph.com/account/info/hg)
2. 复制 `content` 字段的值
3. 使用 `/sklandlogin <token>` 登录

## 安装

```bash
cd /path/to/astrbot/plugins
git clone https://github.com/Azincc/astrbot_plugin_sklandv2.git
```

## 依赖

- httpx>=0.25.0
- pycryptodome>=3.19.0
- apscheduler>=3.10.0

## 许可

MIT License