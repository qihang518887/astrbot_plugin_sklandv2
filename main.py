"""
AstrBot Plugin - Skland V2 (森空岛)

Commands:
- /skland help - 帮助
- /skland login <token> - 登录并签到
- /skland qrcode - 扫码登录
- /skland logout - 登出
- /skland sign - 手动签到
- /skland status - 签到状态
- /skland card - 绑定角色
- /skland arkgacha - 明日方舟抽卡
- /skland endgacha - 终末地抽卡
- /skland import - 自动导入抽卡
- /skland group - 群签到订阅
- /skland users - 用户统计

Config:
- auto_sign_enabled: 自动签到开关
- auto_sign_hour: 自动签到时间
"""

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.config import put_config
import astrbot.api.message_components as Comp
import asyncio
import random
import json

from .skland_api import SklandAPI, UserBinding, Credential, logger as api_logger

PLUGIN_NAME = "astrbot_plugin_sklandv2"
GACHA_API_SEMAPHORE = asyncio.Semaphore(3)


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

        await self._notify_subscribed_groups(users)

    async def _notify_subscribed_groups(self, users: dict):
        groups = await self.get_kv_data("sklandv2_groups", {})
        if not groups:
            return

        success_total = 0
        fail_total = 0
        for user_id, user_data in users.items():
            if user_data.get("last_sign"):
                ls = user_data.get("last_sign", {})
                if ls.get("arknights") or ls.get("endfield"):
                    success_total += 1
                else:
                    fail_total += 1
            else:
                fail_total += 1

        summary = (
            f"✅ skland今日自动签到已完成！\n"
            f"📝 本群共签到成功{success_total}人，共签到失败{fail_total}人。"
        )

        for group_id, info in groups.items():
            try:
                message_chain = MessageChain().message(summary)
                await self.context.send_message(info.get("umo"), message_chain)
            except Exception as e:
                logger.error(f"发送群签到汇总失败: {e}")

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
    async def skland(self, event: AstrMessageEvent):
        """森空岛主命令"""
        text = event.message_str.strip()
        parts = text.split()
        if len(parts) <= 1 or len(parts) >= 1 and len(parts) <= 2 and Parts[1] in ("help", "help"):
            yield event.plain_result(self._help_text())
        else:
            yield event.plain_result(self._help_text())

    def _help_text(self) -> str:
        return (
            "🎮 森空岛V2 帮助\n"
            "══════════════════\n"
            "  /skland help - 显示本帮助\n"
            "  /skland login <token> - 登录并自动导入抽卡(私聊)\n"
            "  /skland qrcode - 扫码登录\n"
            "  /skland logout - 登出(私聊)\n"
            "  /skland sign - 手动签到\n"
            "  /skland status - 签到状态\n"
            "  /skland card - 绑定角色\n"
            "  /skland arkgacha - 明日方舟抽卡\n"
            "  /skland endgacha - 终末地抽卡\n"
            "  /skland import - 自动导入抽卡\n"
            "  /skland group - 群签到订阅\n"
            "  /skland users - 用户统计(管理)\n"
            "══════════════════\n"
            "💡 登录后会自动导入抽卡记录\n"
            "获取Token: 打开\n"
            "https://web-api.hypergryph.com/account/info/hg\n"
            "复制 content 字段"
        )

    # ---------- login ----------
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
                "3. 使用 /skland login <token> 登录"
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
            asyncio.create_task(self._auto_import_all_gacha(token, event))
        except Exception as e:
            logger.error(f"sklandlogin失败: {e}")
            yield event.plain_result(f"❌ 登录失败: {str(e)}")

    # ---------- qrcode ----------
    @filter.command("sklandqrcode")
    async def skland_qrcode(self, event: AstrMessageEvent):
        yield event.plain_result("正在获取二维码，请稍候...")
        try:
            scan_id = await self.api.get_scan()
            scan_url = f" hypergryph://scan_login?scanId={scan_id}"

            import qrcode
            from io import BytesIO
            qr = qrcode.make(scan_url)
            buf = BytesIO()
            qr.save(buf, format='PNG')
            buf.seek(0)

            yield event.plain_result("请使用森空岛APP扫描二维码登录\n二维码有效时间2分钟")
            yield event.chain_result([Comp.Image.fromBytes(buf.getvalue())])

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
                    yield event.plain_result(f"✅ 扫码成功！\n{self._format_sign_status(results, nickname)}\n正在自动导入抽卡记录...")
                    asyncio.create_task(self._auto_import_all_gacha(token, event))
                    return

            yield event.plain_result("❌ 二维码已超时，请重新获取")
        except Exception as e:
            logger.error(f"扫码登录失败: {e}")
            yield event.plain_result(f"❌ 扫码登录失败: {str(e)}")

    # ---------- logout ----------
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
            yield event.plain_result("✅ 已退出登录")
        else:
            yield event.plain_result("您尚未绑定森空岛账号")

    # ---------- sign ----------
    @filter.command("sklandsign")
    async def skland_sign(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
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

    # ---------- status ----------
    @filter.command("sklandstatus")
    async def skland_status(self, event: AstrMessageEvent):
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
                yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
                return

            try:
                token = user_data["token"]
                results, nickname = await self.api.do_full_sign_in(token)
                yield event.plain_result(self._format_sign_status(results, nickname))
            except Exception as e:
                yield event.plain_result(f"❌ 查询失败: {str(e)}")

    # ---------- card ----------
    @filter.command("sklandcard")
    async def skland_card(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
            return

        yield event.plain_result("正在查询角色卡片，请稍候...")
        try:
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

            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"查询卡片失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    # ---------- arkgacha ----------
    @filter.command("sklandarkgacha")
    async def skland_arkgacha(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
            return

        yield event.plain_result("正在查询明日方舟抽卡记录，请稍候...")
        try:
            token = user_data["token"]
            access_token = user_data.get("access_token", token)

            # Step 1: 获取 web token (type=1) 用于 role token API
            grant_code_web = await self.api.get_grant_code(access_token, 1)

            # Step 2: 获取 skland code (type=0) 用于获取绑定列表
            grant_code_skland = await self.api.get_grant_code(access_token, 0)
            cred = await self.api.get_credential(grant_code_skland)
            bindings = await self.api.get_binding_list(cred)

            ark_binding = None
            for b in bindings:
                if b.app_code == "arknights":
                    ark_binding = b
                    break

            if not ark_binding:
                yield event.plain_result("❌ 未绑定明日方舟角色")
                return

            role_token = await self.api.get_role_token(ark_binding.uid, grant_code_web)
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
                    yield event.chain_result([Comp.Image.fromBytes(img_data)])
                else:
                    yield event.plain_result(self._format_gacha_text(pools, total_pulls, six_rate))
            except Exception as e:
                yield event.plain_result(self._format_gacha_text(pools, total_pulls, six_rate))
        except Exception as e:
            logger.error(f"查询抽卡失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    # ---------- endgacha ----------
    @filter.command("sklandendgacha")
    async def skland_endgacha(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
            return

        yield event.plain_result("正在查询终末地抽卡记录，请稍候...")
        try:
            token = user_data["token"]
            access_token = user_data.get("access_token", token)

            # Step 1: 获取 web token (type=1) 用于 role token API
            grant_code_web = await self.api.get_grant_code(access_token, 1)

            # Step 2: 获取 skland code (type=0) 用于获取绑定列表
            grant_code_skland = await self.api.get_grant_code(access_token, 0)
            cred = await self.api.get_credential(grant_code_skland)
            bindings = await self.api.get_binding_list(cred)

            ef_binding = None
            for b in bindings:
                if b.app_code == "endfield":
                    ef_binding = b
                    break

            if not ef_binding:
                yield event.plain_result("❌ 未绑定终末地角色")
                return

            ef_records = []
            for role in ef_binding.roles:
                role_token = await self.api.get_role_token(ef_binding.uid, grant_code_web)
                server_id = role.get("serverId", ef_binding.uid)
                for pool_type_raw in ("char", "weapon"):
                    try:
                        is_weapon = pool_type_raw == "weapon"
                        ef_gacha_url = "https://ef-webview.hypergryph.com/api/record/weapon" if is_weapon else "https://ef-webview.hypergryph.com/api/record/char"
                        params = {"token": role_token, "server_id": server_id, "lang": "zh-cn"}
                        client = await self.api._get_client()
                        response = await client.get(ef_gacha_url, params=params)
                        data = response.json()
                        if data.get("code") == 0 and data.get("data"):
                            gacha_list = data["data"].get("gachaList") or data["data"].get("list", [])
                            for item in (gacha_list or []):
                                ef_records.append(item)
                    except Exception:
                        continue

            if not ef_records:
                yield event.plain_result("❌ 暂无终末地抽卡记录")
                return

            pools_dict = {}
            for record in ef_records[:100]:
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

            total_pulls = len(ef_records)
            yield event.plain_result(self._format_gacha_text(pools, total_pulls, 0))
        except Exception as e:
            logger.error(f"查询终末地抽卡失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    # ---------- gacha helpers ----------
    def _format_gacha_text(self, pools: list, total: int, six_rate: float) -> str:
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

    async def _auto_import_all_gacha(self, token: str, event: AstrMessageEvent):
        async with GACHA_API_SEMAPHORE:
            try:
                user_id = event.get_sender_id()
                users = await self.get_kv_data("sklandv2_users", {})
                user_data = users.get(user_id)
                if not user_data:
                    return

                logger.info(f"[auto_import] 开始为用户 {user_id} 自动导入抽卡记录")

                access_token = user_data.get("access_token", token)
                logger.debug(f"[auto_import] access_token: {access_token[:8]}...")

                # Step 1: 获取 skland 授权码 (token_type=0) -> 获取 cred -> 获取绑定列表
                grant_code_skland = await self.api.get_grant_code(access_token, 0)
                logger.debug(f"[auto_import] grant_code_skland: {grant_code_skland[:8]}...")
                cred = await self.api.get_credential(grant_code_skland)
                logger.debug(f"[auto_import] cred obtained, cred_token: {cred.token[:8]}...")
                bindings = await self.api.get_binding_list(cred)
                logger.info(f"[auto_import] 获取到 {len(bindings)} 个绑定")

                ak_records = []
                ef_records = []

                for binding in bindings:
                    if binding.app_code == "arknights":
                        # Step 2: 获取 hypergryph pass token (token_type=1)
                        grant_code_web = await self.api.get_grant_code(access_token, 1)
                        logger.debug(f"[auto_import] {binding.nickname}: grant_code_web: {grant_code_web[:8]}...")

                        # Step 3: 用 pass token 和 binding.uid 获取 role token
                        role_token = await self.api.get_role_token(binding.uid, grant_code_web)
                        logger.info(f"[auto_import] {binding.nickname} role_token 获取成功")

                        # Step 4: 获取 AK cookie
                        ak_cookie = await self.api.get_ak_cookie(role_token)
                        logger.info(f"[auto_import] ak_cookie: {'获取成功' if ak_cookie else '获取失败'}")

                        # Step 5: 获取抽卡类别并拉取记录
                        categories = await self.api.get_gacha_categories(
                            binding.uid, role_token, access_token, ak_cookie
                        )
                        logger.info(f"[auto_import] 获取到 {len(categories)} 个抽卡类别")
                        for cate in categories[:3]:
                            cate_id = str(cate.get("id"))
                            logger.debug(f"[auto_import] 获取卡池 {cate_id}")
                            records = await self.api.get_all_gacha_records(
                                binding.uid, role_token, access_token, ak_cookie, cate_id
                            )
                            ak_records.extend(records)

                    elif binding.app_code == "endfield":
                        grant_code_web = await self.api.get_grant_code(access_token, 1)
                        role_token = await self.api.get_role_token(binding.uid, grant_code_web)
                        for role in binding.roles:
                            server_id = role.get("serverId", binding.uid)
                            for pool_type_raw in ("char", "weapon"):
                                try:
                                    is_weapon = pool_type_raw == "weapon"
                                    ef_gacha_url = "https://ef-webview.hypergryph.com/api/record/weapon" if is_weapon else "https://ef-webview.hypergryph.com/api/record/char"
                                    params = {"token": role_token, "server_id": server_id, "lang": "zh-cn"}
                                    client = await self.api._get_client()
                                    response = await client.get(ef_gacha_url, params=params)
                                    data = response.json()
                                    if data.get("code") == 0 and data.get("data"):
                                        gacha_list = data["data"].get("gachaList") or data["data"].get("list", [])
                                        for item in (gacha_list or []):
                                            ef_records.append(item)
                                except Exception as inner_e:
                                    logger.error(f"[auto_import] 终末地抽卡拉取失败: {inner_e}")

                summary_parts = []
                if ak_records:
                    summary_parts.append(f"明日方舟{len(ak_records)}条")
                if ef_records:
                    summary_parts.append(f"终末地{len(ef_records)}条")

                if summary_parts:
                    gacha_records = await self.get_kv_data("sklandv2_gacha", {})
                    gacha_records[user_id] = {
                        "arknights": [
                            {
                                "poolName": r.get("poolName", ""),
                                "charName": r.get("charName", ""),
                                "rarity": r.get("rarity", 3),
                                "isNew": r.get("isNew", False),
                            }
                            for r in ak_records[:200]
                        ],
                        "endfield": [r for r in ef_records[:200]],
                    }
                    await self.put_kv_data("sklandv2_gacha", gacha_records)
                    logger.info(f"[auto_import] 保存 {len(ak_records)} 条方舟记录, {len(ef_records)} 条终末地记录")
                    await self._send_private_message(user_id, user_data, f"📥 自动导入抽卡记录完成：\n{', '.join(summary_parts)}")
                else:
                    await self._send_private_message(user_id, user_data, "📥 未发现抽卡记录")
                    logger.info(f"[auto_import] 未发现任何抽卡记录")
            except Exception as e:
                logger.error(f"自动导入抽卡记录失败: {e}")
                logger.exception("[auto_import] 完整异常信息:")

    # ---------- import ----------
    @filter.command("sklandimport")
    async def skland_import(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        users = await self.get_kv_data("sklandv2_users", {})
        user_data = users.get(user_id)

        if not user_data:
            yield event.plain_result("❌ 您尚未绑定，请先使用 /skland login <token> 登录")
            return

        yield event.plain_result("正在自动导入抽卡记录，请稍候...")
        try:
            token = user_data["token"]
            access_token = user_data.get("access_token", token)
            grant_code_web = await self.api.get_grant_code(access_token, 1)
            grant_code_skland = await self.api.get_grant_code(access_token, 0)
            cred = await self.api.get_credential(grant_code_skland)
            bindings = await self.api.get_binding_list(cred)

            import_results = []
            for binding in bindings:
                if binding.app_code == "arknights":
                    role_token = await self.api.get_role_token(binding.uid, grant_code_web)
                    ak_cookie = await self.api.get_ak_cookie(role_token)
                    categories = await self.api.get_gacha_categories(
                        binding.uid, role_token, access_token, ak_cookie
                    )
                    ark_records = []
                    for cate in categories[:3]:
                        cate_id = str(cate.get("id"))
                        records = await self.api.get_all_gacha_records(
                            binding.uid, role_token, access_token, ak_cookie, cate_id
                        )
                        ark_records.extend(records)
                    import_results.append(("明日方舟", len(ark_records), ark_records))

                elif binding.app_code == "endfield":
                    role_token = await self.api.get_role_token(binding.uid, grant_code_web)
                    ef_records = []
                    for role in binding.roles:
                        server_id = role.get("serverId", binding.uid)
                        for pool_type_raw in ("char", "weapon"):
                            try:
                                is_weapon = pool_type_raw == "weapon"
                                ef_gacha_url = "https://ef-webview.hypergryph.com/api/record/weapon" if is_weapon else "https://ef-webview.hypergryph.com/api/record/char"
                                params = {"token": role_token, "server_id": server_id, "lang": "zh-cn"}
                                client = await self.api._get_client()
                                response = await client.get(ef_gacha_url, params=params)
                                data = response.json()
                                if data.get("code") == 0 and data.get("data"):
                                    gacha_list = data["data"].get("gachaList") or data["data"].get("list", [])
                                    for item in (gacha_list or []):
                                        ef_records.append(item)
                            except Exception:
                                continue
                    import_results.append(("终末地", len(ef_records), ef_records))

            summary = []
            for game, count, records in import_results:
                summary.append(f"{game} {count}条")
                gacha_records = await self.get_kv_data("sklandv2_gacha", {})
                gacha_records[user_id] = gacha_records.get(user_id, {})
                gacha_records[user_id]["arknights" if game == "明日方舟" else "endfield"] = records
                await self.put_kv_data("sklandv2_gacha", gacha_records)

            if summary:
                yield event.plain_result(f"📥 自动导入抽卡记录完成：\n{', '.join(summary)}")
            else:
                yield event.plain_result("📥 未发现新抽卡记录")
        except Exception as e:
            logger.error(f"自动导入抽卡失败: {e}")
            yield event.plain_result(f"❌ 自动导入失败: {str(e)}")

    # ---------- group ----------
    @filter.command("sklandgroup")
    async def skland_group(self, event: AstrMessageEvent):
        group_id = getattr(event.message_obj, "group_id", None)
        if not group_id:
            yield event.plain_result("请在群内使用此命令")
            return

        groups = await self.get_kv_data("sklandv2_groups", {})
        gid = str(group_id)
        if gid in groups:
            del groups[gid]
            await self.put_kv_data("sklandv2_groups", groups)
            yield event.plain_result("✅ 已取消本群签到通知订阅")
        else:
            groups[gid] = {
                "umo": event.unified_msg_origin,
                "name": f"群{group_id}",
            }
            await self.put_kv_data("sklandv2_groups", groups)
            yield event.plain_result("✅ 已订阅每日签到通知")

    # ---------- users ----------
    @filter.command("sklandusers")
    async def skland_users(self, event: AstrMessageEvent):
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