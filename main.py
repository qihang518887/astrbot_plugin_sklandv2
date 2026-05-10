"""
AstrBot Plugin - Skland V2 (森空岛)

Commands:
- skland: 查看帮助
- sklandlogin: 登录并签到
- sklandlogout: 登出
- sklandcard: 查询角色卡片
- sklandrogue: 查询肉鸽战绩
- sklandsign: 手动签到

Config:
- auto_sign_enabled: 自动签到开关
- auto_sign_hour: 自动签到时间
"""

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from astrbot.core.star.filter.permission import PermissionType
import astrbot.api.message_components as Comp
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.config import put_config
import asyncio
import random
import json

from .skland_api import SklandAPI, UserBinding, Credential

PLUGIN_NAME = "astrbot_plugin_sklandv2"


@register(PLUGIN_NAME, "AstrBot", "森空岛V2插件(明日方舟/终末地)", "2.0.0")
class SklandPluginV2(Star):
    """森空岛签到和数据查询插件V2"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.api = SklandAPI(max_retries=3)
        self.scheduler = AsyncIOScheduler()
        self._init_config()

    def _init_config(self):
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到开关",
            key="auto_sign_enabled",
            value=True,
            description="开启后，将在指定时间自动为所有已注册用户签到"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="自动签到时间(小时)",
            key="auto_sign_hour",
            value=1,
            description="自动签到执行的小时(0-23)"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="显示玩家名称",
            key="show_player_name",
            value=True,
            description="开启后显示森空岛昵称"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="签到随机延迟",
            key="auto_sign_delay",
            value=10,
            description="自动签到随机延时秒数"
        )
        put_config(
            namespace=PLUGIN_NAME,
            name="最大用户数",
            key="max_users",
            value=10,
            description="最大绑定用户数，0为无限制"
        )

    def _get_config(self) -> dict:
        return {
            "auto_sign_enabled": self.config.get("auto_sign_enabled", True),
            "auto_sign_hour": self.config.get("auto_sign_hour", 1),
            "show_player_name": self.config.get("show_player_name", True),
            "auto_sign_delay": self.config.get("auto_sign_delay", 10),
            "max_users": self.config.get("max_users", 10),
        }

    async def initialize(self):
        logger.info("森空岛V2插件已加载")
        config = self._get_config()
        if config.get("auto_sign_enabled", False):
            hour = config.get("auto_sign_hour", 1)
            self._start_auto_sign_job(hour)
        if not self.scheduler.running:
            self.scheduler.start()

    async def terminate(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
        await self.api.close()
        logger.info("森空岛V2插件已卸载")

    def _start_auto_sign_job(self, hour: int = 1):
        hour = max(0, min(23, hour))
        trigger = CronTrigger(hour=hour, minute=0)
        try:
            self.scheduler.remove_job("sklandv2_auto_sign")
        except Exception:
            pass

        self.scheduler.add_job(
            self._auto_sign_all_users,
            trigger=trigger,
            id="sklandv2_auto_sign",
            misfire_grace_time=3600,
        )
        logger.info(f"森空岛V2自动签到任务已启动，每天{hour:02d}:00执行")

    async def _auto_sign_all_users(self):
        config = self._get_config()
        if not config.get("auto_sign_enabled", False):
            logger.info("自动签到已关闭")
            return

        logger.info("开始执行自动签到...")
        users = await self.get_kv_data("sklandv2_users", {})
        if not users:
            logger.info("没有已注册用户")
            return

        max_delay = config.get("auto_sign_delay", 10)

        for user_id, user_data in users.items():
            if max_delay > 0:
                delay = random.uniform(0, max_delay)
                logger.info(f"等待 {delay:.2f} 秒")
                await asyncio.sleep(delay)

            if "token" not in user_data:
                continue

            try:
                token = user_data["token"]
                results, nickname = await self.api.do_full_sign_in(token)

                for r in results:
                    if r.game == "明日方舟" and self._is_signed_today(r):
                        user_data.setdefault("last_sign", {})["arknights"] = datetime.now().strftime("%Y-%m-%d")
                    elif r.game == "终末地" and self._is_signed_today(r):
                        user_data.setdefault("last_sign", {})["endfield"] = datetime.now().strftime("%Y-%m-%d")

                message = f"🎮 森空岛自动签到结果\n\n{self._format_sign_status(results, nickname)}"
                await self._send_private_message(user_id, user_data, message)
                users[user_id] = user_data
                logger.info(f"用户 {user_id} ({nickname}) 自动签到完成")
            except Exception as e:
                logger.error(f"用户 {user_id} 自动签到失败: {e}")
                message = f"⚠️ 自动签到失败\n错误: {str(e)}\n请重新登录"
                await self._send_private_message(user_id, user_data, message)

        await self.put_kv_data("sklandv2_users", users)
        logger.info("自动签到执行完毕")

    async def _send_private_message(self, user_id: str, user_data: dict, message: str):
        try:
            umo = user_data.get("umo")
            if not umo:
                return

            message_chain = MessageChain().message(message)
            await self.context.send_message(umo, message_chain)
        except Exception as e:
            logger.error(f"发送私聊消息失败: {e}")

    def _is_signed_today(self, result) -> bool:
        if result.success:
            return True
        error = result.error.lower() if result.error else ""
        return any(k in error for k in ["已签到", "请勿重复", "重复签到", "already", "签到过", "今日已"])

    def _format_sign_status(self, results: list, nickname: str = "") -> str:
        if not results:
            return "没有绑定游戏"
        lines = []
        if nickname:
            lines.append(f"【{nickname}】")
        for r in results:
            if r.success or self._is_signed_today(r):
                award = ", ".join(r.awards) if getattr(r, "awards", None) else "无奖励"
                lines.append(f"{r.game} ✅ ({award})")
            else:
                lines.append(f"{r.game} ❌: {r.error}")
        return "\n".join(lines)

    @filter.command("skland")
    async def skland_help(self, event: AstrMessageEvent):
        """森空岛V2帮助"""
        yield event.plain_result(
            "🎮 森空岛V2 帮助\n"
            "══════════════════\n"
            "📝 命令列表:\n"
            "  /skland - 显示本帮助\n"
            "  /sklandlogin <token> - 登录并签到\n"
            "  /sklandqrcode - 扫码登录(私聊)\n"
            "  /sklandlogout - 登出\n"
            "  /sklandsign - 手动签到\n"
            "  /sklandcard - 查询角色卡片\n"
            "  /sklandrogue <主题> - 查询肉鸽战绩\n"
            "  /sklandstatus - 查看签到状态\n"
            "  /sklandgacha - 查询抽卡记录\n"
            "  /sklandimport <url> - 导入抽卡记录\n"
            "  /sklandusers - 用户统计(管理员)\n"
            "══════════════════\n"
            "📌 获取Token方法:\n"
            "  1. 登录 https://web-api.hypergryph.com/account/info/hg\n"
            "  2. 复制 content 字段的值\n"
            "  3. 使用 /sklandlogin <token> 登录"
        )

    @filter.command("sklandlogin")
    async def skland_login(self, event: AstrMessageEvent, token: str = ""):
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id:
            yield event.plain_result("请在私聊中使用此命令\n为保护隐私，请撤回群内消息")
            return

        config = self._get_config()
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        max_users = config.get("max_users", 10)

        if user_id not in users and max_users > 0 and len(users) >= max_users:
            yield event.plain_result(f"❌ 绑定失败：已达到最大用户数限制({max_users}个)")
            return

        token = token.strip()
        if not token:
            yield event.plain_result(
                "请先获取token:\n"
                "1. 登录 https://web-api.hypergryph.com/account/info/hg\n"
                "2. 复制 content 字段的值\n"
                "3. 使用 /sklandlogin <token> 登录"
            )
            return

        yield event.plain_result("正在登录并签到，请稍候...")
        try:
            results, nickname = await self.api.do_full_sign_in(token)
            user_data = {
                "token": token,
                "nickname": nickname,
                "last_username": event.get_sender_name(),
                "last_sign": {},
                "bound_at": datetime.now().isoformat(),
                "umo": event.unified_msg_origin,
            }
            for r in results:
                if r.game == "明日方舟" and self._is_signed_today(r):
                    user_data["last_sign"]["arknights"] = datetime.now().strftime("%Y-%m-%d")
                elif r.game == "终末地" and self._is_signed_today(r):
                    user_data["last_sign"]["endfield"] = datetime.now().strftime("%Y-%m-%d")

            all_users = await self.get_kv_data("sklandv2_users", {})
            all_users[user_id] = user_data
            await self.put_kv_data("sklandv2_users", all_users)

            yield event.plain_result(f"✅ 登录成功！\n{self._format_sign_status(results, nickname)}")
        except Exception as e:
            logger.error(f"sklandlogin失败: {e}")
            yield event.plain_result(f"❌ 登录失败: {str(e)}")

    @filter.command("sklandlogout")
    async def skland_logout(self, event: AstrMessageEvent):
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id:
            yield event.plain_result("请在私聊中使用此命令")
            return

        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        if user_id in users:
            del users[user_id]
            await self.put_kv_data("sklandv2_users", users)
            yield event.plain_result("✅ 已退出登录并清除绑定信息")
        else:
            yield event.plain_result("您尚未绑定森空岛账号")

    @filter.command("sklandqrcode")
    async def skland_qrcode(self, event: AstrMessageEvent):
        """扫码登录森空岛"""
        group_id = getattr(event.message_obj, "group_id", None)
        if group_id:
            yield event.plain_result("请在私聊中使用此命令进行扫码登录")
            return

        yield event.plain_result("正在获取二维码，请稍候...")
        try:
            scan_id = await self.api.get_scan()
            scan_url = f"hypergryph://scan_login?scanId={scan_id}"

            import qrcode
            from io import BytesIO
            qr = qrcode.make(scan_url)
            buf = BytesIO()
            qr.save(buf, format='PNG')
            buf.seek(0)

            yield event.plain_result("请使用森空岛APP扫描二维码登录\n二维码有效时间2分钟")
            yield event.image_result(buf.getvalue())

            import asyncio
            for _ in range(60):
                await asyncio.sleep(2)
                scan_code = await self.api.get_scan_status(scan_id)
                if scan_code:
                    token = await self.api.get_token_by_scan_code(scan_code)

                    results, nickname = await self.api.do_full_sign_in(token)
                    user_id = event.get_sender_id()
                    users = await self.get_kv_data("sklandv2_users", {})
                    users[user_id] = {
                        "token": token,
                        "nickname": nickname,
                        "last_username": event.get_sender_name(),
                        "last_sign": {},
                        "bound_at": datetime.now().isoformat(),
                        "umo": event.unified_msg_origin,
                    }
                    for r in results:
                        if r.game == "明日方舟" and self._is_signed_today(r):
                            users[user_id]["last_sign"]["arknights"] = datetime.now().strftime("%Y-%m-%d")
                        elif r.game == "终末地" and self._is_signed_today(r):
                            users[user_id]["last_sign"]["endfield"] = datetime.now().strftime("%Y-%m-%d")
                    await self.put_kv_data("sklandv2_users", users)
                    yield event.plain_result(f"✅ 扫码成功！\n{self._format_sign_status(results, nickname)}")
                    return

            yield event.plain_result("❌ 二维码已超时，请重新获取")
        except Exception as e:
            logger.error(f"扫码登录失败: {e}")
            yield event.plain_result(f"❌ 扫码登录失败: {str(e)}")

    @filter.command("sklandsign")
    async def skland_sign(self, event: AstrMessageEvent):
        """手动签到"""
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
            return

        yield event.plain_result("正在签到，请稍候...")
        try:
            token = user_data["token"]
            results, nickname = await self.api.do_full_sign_in(token)

            for r in results:
                if r.game == "明日方舟" and self._is_signed_today(r):
                    user_data.setdefault("last_sign", {})["arknights"] = datetime.now().strftime("%Y-%m-%d")
                elif r.game == "终末地" and self._is_signed_today(r):
                    user_data.setdefault("last_sign", {})["endfield"] = datetime.now().strftime("%Y-%m-%d")

            users[user_id] = user_data
            await self.put_kv_data("sklandv2_users", users)

            yield event.plain_result(self._format_sign_status(results, nickname))
        except Exception as e:
            logger.error(f"签到失败: {e}")
            yield event.plain_result(f"❌ 签到失败: {str(e)}")

    @filter.command("sklandstatus")
    async def skland_status(self, event: AstrMessageEvent):
        """查看签到状态"""
        user_id = event.get_sender_id()
        group_id = getattr(event.message_obj, "group_id", None)
        users = await self.get_kv_data("sklandv2_users", {})

        if group_id:
            group_users = (await self.get_kv_data("sklandv2_groups", {})).get(group_id, [])
            message_lines = ["📊 森空岛签到统计", "═══════════════", "方舟 | 终末 | 昵称", "-----------------"]

            for uid in group_users:
                user_data = users.get(uid)
                if not user_data:
                    continue
                try:
                    results, nickname = await self.api.do_full_sign_in(user_data["token"])

                    config = self._get_config()
                    if not config.get("show_player_name", True) or not nickname:
                        nickname = user_data.get("last_username", "未知")

                    ak_signed = user_data.get("last_sign", {}).get("arknights")
                    ef_signed = user_data.get("last_sign", {}).get("endfield")
                    ak_icon = "✅" if ak_signed else "❌"
                    ef_icon = "✅" if ef_signed else "❌"
                    message_lines.append(f" {ak_icon} | {ef_icon} | {nickname}")
                except:
                    message_lines.append(" ⚠️ | ⚠️ | (Error)")

            yield event.plain_result("\n".join(message_lines))
        else:
            user_data = users.get(user_id)
            if not user_data:
                yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
                return

            try:
                token = user_data["token"]
                results, nickname = await self.api.do_full_sign_in(token)
                yield event.plain_result(self._format_sign_status(results, nickname))
            except Exception as e:
                yield event.plain_result(f"❌ 查询失败: {str(e)}")

    @filter.command("sklandcard")
    async def skland_card(self, event: AstrMessageEvent):
        """查询角色卡片"""
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
            return

        yield event.plain_result("正在查询角色卡片，请稍候...")
        try:
            from .skland_api import Credential

            token = user_data["token"]
            auth_code = await self.api.get_authorization(token)
            cred = await self.api.get_credential(auth_code)
            bindings = await self.api.get_binding_list(cred)

            if not bindings:
                yield event.plain_result("❌ 没有找到绑定角色")
                return

            lines = ["📋 绑定的角色", "═══════════════"]
            for binding in bindings:
                line = f"🎮 {binding.game_name}\n"
                line += f"   昵称: {binding.nickname}\n"
                line += f"   UID: {binding.uid}\n"
                line += f"   渠道: {binding.channel_name}"
                lines.append(line)

            await self.put_kv_data("sklandv2_users", users)
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"查询卡片失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    @filter.command("sklandrogue")
    async def skland_rogue(self, event: AstrMessageEvent, topic: str = ""):
        """查询肉鸽战绩"""
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
            return

        topic_id = self._get_topic_id(topic)
        if not topic_id:
            yield event.plain_result(
                "请指定肉鸽主题:\n"
                "/sklandrogue 傀影\n"
                "/sklandrogue 水月\n"
                "/sklandrogue 萨米\n"
                "/sklandrogue 萨卡兹\n"
                "/sklandrogue 界园"
            )
            return

        yield event.plain_result("正在查询肉鸽战绩，请稍候...")
        try:
            from .skland_api import Credential

            token = user_data["token"]
            auth_code = await self.api.get_authorization(token)
            cred = await self.api.get_credential(auth_code)
            bindings = await self.api.get_binding_list(cred)

            ark_binding = None
            for b in bindings:
                if b.app_code == "arknights":
                    ark_binding = b
                    break

            if not ark_binding:
                yield event.plain_result("❌ 未绑定明日方舟角色")
                return

            rogue_data = await self.api.get_rogue_data(cred, ark_binding.uid, topic_id)
            if not rogue_data:
                yield event.plain_result("❌ 查询肉鸽数据失败")
                return

            lines = [f"📊 肉鸽战绩 - {topic}", "═══════════════"]

            if "recentScore" in rogue_data:
                score = rogue_data["recentScore"]
                lines.append(f"最近一次:")
                lines.append(f"  通关: {'是' if score.get('isCompleted') else '否'}")
                lines.append(f"  招募数: {score.get('recruitNum', 0)}")
                lines.append(f"  剧情数: {score.get('talkNum', 0)}")

            if "bestScore" in rogue_data:
                best = rogue_data["bestScore"]
                lines.append(f"\n最高记录:")
                lines.append(f"  通关: {'是' if best.get('isCompleted') else '否'}")

            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"查询肉鸽失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    def _get_topic_id(self, topic: str) -> str:
        topic_map = {
            "傀影": "phantom",
            "水月": "mizuki",
            "萨米": "sami",
            "萨卡兹": "sarkaz",
            "界园": "zoo",
        }
        return topic_map.get(topic, "")

    @filter.command("sklandusers")
    async def skland_users(self, event: AstrMessageEvent):
        """查看用户统计(仅管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可用")
            return

        users = await self.get_kv_data("sklandv2_users", {})
        config = self._get_config()
        max_users = config.get("max_users", 10)

        lines = [
            "📊 森空岛V2 用户统计",
            "═══════════════════",
            f"📝 总用户: {len(users)} 人",
        ]

        if max_users > 0:
            remaining = max(0, max_users - len(users))
            lines.append(f"🎯 最大限制: {max_users} 人")
            lines.append(f"🆓 剩余名额: {remaining} 人")

        if len(users) <= 20:
            lines.append("\n👤 用户列表:")
            for uid, udata in users.items():
                nickname = udata.get("nickname") or udata.get("last_username", "未知")
                last_sign = list(udata.get("last_sign", {}).values())[-1] if udata.get("last_sign") else "未签到"
                lines.append(f"  • {nickname} (最后: {last_sign})")

        yield event.plain_result("\n".join(lines))

    @filter.command("sklandgacha")
    async def skland_gacha(self, event: AstrMessageEvent):
        """查询抽卡记录"""
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
            return

        yield event.plain_result("正在查询抽卡记录，请稍候...")
        try:
            token = user_data["token"]
            access_token = user_data.get("access_token", token)

            auth_code = await self.api.get_grant_code(access_token, 1)
            cred = await self.api.get_credential(auth_code)
            bindings = await self.api.get_binding_list(cred)

            ark_binding = None
            for b in bindings:
                if b.app_code == "arknights":
                    ark_binding = b
                    break

            if not ark_binding:
                yield event.plain_result("❌ 未绑定明日方舟角色")
                return

            role_token = await self.api.get_role_token(ark_binding.uid, auth_code)
            ak_cookie = await self.api.get_ak_cookie(role_token)

            categories = await self.api.get_gacha_categories(
                ark_binding.uid, role_token, access_token, ak_cookie
            )

            if not categories:
                yield event.plain_result("❌ 无法获取抽卡类别")
                return

            all_records = []
            for cate in categories[:3]:
                cate_id = cate.get("id") or cate.get("cateId")
                if cate_id:
                    records = await self.api.get_all_gacha_records(
                        ark_binding.uid, role_token, access_token, ak_cookie, str(cate_id)
                    )
                    all_records.extend(records)

            if not all_records:
                yield event.plain_result("❌ 暂无抽卡记录")
                return

            pools_dict = {}
            for record in all_records[:100]:
                pool_name = record.get("poolName", "未知")
                if pool_name not in pools_dict:
                    pools_dict[pool_name] = []
                pools_dict[pool_name].append({
                    "name": record.get("charName", "未知"),
                    "rarity": record.get("rarity", 3),
                    "is_new": record.get("isNew", False),
                })

            pools = []
            for name, pulls in pools_dict.items():
                pools.append({
                    "name": name[:20],
                    "count": len(pulls),
                    "pulls": pulls[:20]
                })

            total_pulls = len(all_records)
            six_count = sum(1 for r in all_records if r.get("rarity", 0) >= 5)
            six_rate = (six_count / total_pulls * 100) if total_pulls > 0 else 0

            try:
                from .render import render_gacha_history
                img_data = await render_gacha_history(
                    nickname=ark_binding.nickname,
                    server="官服" if ark_binding.game_id == 1 else "B服",
                    avatar_url="https://prts.wiki/images/avator/char_001_chen.png",
                    level=user_data.get("level", 1),
                    pools=pools,
                    total_pulls=total_pulls,
                    six_rate=round(six_rate, 1),
                    up_rate=0,
                )

                if img_data:
                    yield event.image_result(img_data)
                else:
                    yield event.plain_result(self._format_gacha_text(pools, total_pulls, six_rate))
            except Exception as e:
                logger.error(f"渲染图片失败: {e}")
                yield event.plain_result(self._format_gacha_text(pools, total_pulls, six_rate))

        except Exception as e:
            logger.error(f"查询抽卡记录失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    def _format_gacha_text(self, pools: list, total: int, six_rate: float) -> str:
        """格式化抽卡记录为文本"""
        lines = [
            f"📊 抽卡记录统计",
            f"═══════════════",
            f"总抽数: {total}",
            f"六星率: {six_rate:.1f}%",
            "",
        ]
        for pool in pools[:5]:
            lines.append(f"【{pool['name']}】{pool['count']}抽")
            pulls_str = ", ".join([p["name"] for p in pool["pulls"][:8]])
            lines.append(f"  {pulls_str}")
            if len(pool["pulls"]) > 8:
                lines.append(f"  ... 共{len(pool['pulls'])}个")
            lines.append("")
        return "\n".join(lines)

    @filter.command("sklandimport")
    async def skland_import(self, event: AstrMessageEvent, url: str = ""):
        """导入抽卡记录"""
        if not url:
            yield event.plain_result(
                "请提供导入链接\n"
                "使用方法: /sklandimport <heybox导出链接>\n"
                "注: 支持heybox导出的抽卡记录链接"
            )
            return

        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /sklandlogin <token> 登录")
            return

        yield event.plain_result("正在导入抽卡记录，请稍候...")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code != 200:
                    yield event.plain_result(f"❌ 请求失败，状态码: {response.status_code}")
                    return

                data = response.json()
                info = data.get("info", {})
                gacha_data = data.get("data", {})

                records = []
                for ts, records_list in gacha_data.items():
                    for idx, item in enumerate(records_list):
                        records.append({
                            "ts": int(ts),
                            "pos": idx,
                            "name": item[0],
                            "rarity": item[1],
                            "is_new": item[2] if len(item) > 2 else False,
                            "pool": "未知"
                        })

                gacha_records = await self.get_kv_data("sklandv2_gacha", {})
                if user_id not in gacha_records:
                    gacha_records[user_id] = []
                gacha_records[user_id].extend(records)
                await self.put_kv_data("sklandv2_gacha", gacha_records)

                yield event.plain_result(
                    f"📥 导入成功\n"
                    f"UID: {info.get('uid')}\n"
                    f"记录数: {len(records)} 条\n"
                    f"数据来源: heybox"
                )
        except Exception as e:
            logger.error(f"导入抽卡记录失败: {e}")
            yield event.plain_result(f"❌ 导入失败: {str(e)}")