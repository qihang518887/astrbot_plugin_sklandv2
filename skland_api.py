"""
Skland API - Ported from Rust implementation and nonebot-plugin-skland
Handles device ID generation, authentication, sign-in, and game data queries
"""

import base64
import gzip
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse
from dataclasses import dataclass

import httpx

logger = logging.getLogger("skland_api")
try:
    from Crypto.Cipher import AES, DES, PKCS1_v1_5
    from Crypto.PublicKey import RSA
    from Crypto.Util.Padding import pad
except ImportError:
    logger.warning("pycryptodome not installed, some features may not work")

USER_AGENT = "Mozilla/5.0 (Linux; Android 12; SM-A5560 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36; SKLand/1.52.1"

DES_RULE = {
    "appId": {"cipher": "DES", "is_encrypt": 1, "key": "uy7mzc4h", "obfuscated_name": "xx"},
    "box": {"is_encrypt": 0, "obfuscated_name": "jf"},
    "canvas": {"cipher": "DES", "is_encrypt": 1, "key": "snrn887t", "obfuscated_name": "yk"},
    "clientSize": {"cipher": "DES", "is_encrypt": 1, "key": "cpmjjgsu", "obfuscated_name": "zx"},
    "organization": {"cipher": "DES", "is_encrypt": 1, "key": "78moqjfc", "obfuscated_name": "dp"},
    "os": {"cipher": "DES", "is_encrypt": 1, "key": "je6vk6t4", "obfuscated_name": "pj"},
    "platform": {"cipher": "DES", "is_encrypt": 1, "key": "pakxhcd2", "obfuscated_name": "gm"},
    "plugins": {"cipher": "DES", "is_encrypt": 1, "key": "v51m3pzl", "obfuscated_name": "kq"},
    "pmf": {"cipher": "DES", "is_encrypt": 1, "key": "2mdeslu3", "obfuscated_name": "vw"},
    "protocol": {"is_encrypt": 0, "obfuscated_name": "protocol"},
    "referer": {"cipher": "DES", "is_encrypt": 1, "key": "y7bmrjlc", "obfuscated_name": "ab"},
    "res": {"cipher": "DES", "is_encrypt": 1, "key": "whxqm2a7", "obfuscated_name": "hf"},
    "rtype": {"cipher": "DES", "is_encrypt": 1, "key": "x8o2h2bl", "obfuscated_name": "lo"},
    "sdkver": {"cipher": "DES", "is_encrypt": 1, "key": "9q3dcxp2", "obfuscated_name": "sc"},
    "status": {"cipher": "DES", "is_encrypt": 1, "key": "2jbrxxw4", "obfuscated_name": "an"},
    "subVersion": {"cipher": "DES", "is_encrypt": 1, "key": "eo3i2puh", "obfuscated_name": "ns"},
    "svm": {"cipher": "DES", "is_encrypt": 1, "key": "fzj3kaeh", "obfuscated_name": "qr"},
    "time": {"cipher": "DES", "is_encrypt": 1, "key": "q2t3odsk", "obfuscated_name": "nb"},
    "timezone": {"cipher": "DES", "is_encrypt": 1, "key": "1uv05lj5", "obfuscated_name": "as"},
    "tn": {"cipher": "DES", "is_encrypt": 1, "key": "x9nzj1bp", "obfuscated_name": "py"},
    "trees": {"cipher": "DES", "is_encrypt": 1, "key": "acfs0xo4", "obfuscated_name": "pi"},
    "ua": {"cipher": "DES", "is_encrypt": 1, "key": "k92crp1t", "obfuscated_name": "bj"},
    "url": {"cipher": "DES", "is_encrypt": 1, "key": "y95hjkoo", "obfuscated_name": "cf"},
    "version": {"is_encrypt": 0, "obfuscated_name": "version"},
    "vpw": {"cipher": "DES", "is_encrypt": 1, "key": "r9924ab5", "obfuscated_name": "ca"},
}

DES_TARGET = {
    "protocol": 102,
    "organization": "UWXspnCCJN4sfYlNfqps",
    "appId": "default",
    "os": "web",
    "version": "3.0.0",
    "sdkver": "3.0.0",
    "box": "",
    "rtype": "all",
    "subVersion": "1.0.0",
    "time": 0,
}

BROWSER_ENV = {
    "plugins": "MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "canvas": "259ffe69",
    "timezone": -480,
    "platform": "Win32",
    "url": "https://www.skland.com/",
    "referer": "",
    "res": "1920_1080_24_1.25",
    "clientSize": "0_0_1080_1920_1920_1080_1920_1080",
    "status": "0011",
}

RSA_PUBLIC_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPixoinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8mN28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjvg0iYWRByfRsK2gdl7llqCwIDAQAB"


@dataclass
class SignInResult:
    success: bool
    game: str
    nickname: str
    channel: str
    awards: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class UserBinding:
    app_code: str
    game_name: str
    nickname: str
    channel_name: str
    uid: str
    game_id: int
    roles: list[dict] = field(default_factory=list)


@dataclass
class Credential:
    token: str
    cred: str


@dataclass
class ArkCard:
    """明日方舟角色卡片数据"""
    nickname: str = ""
    level: int = 0
    uid: str = ""
    tx: int = 0
    ap: int = 0
    rp: int = 0
    recruit: Any = None
    building: Any = None
    chars: list = field(default_factory=list)


@dataclass
class EndfieldCard:
    """终末地角色卡片数据"""
    pass


class SklandAPI:
    """Skland API client with full functionality"""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._did: str | None = None

    def _is_signed_today(self, result: SignInResult) -> bool:
        if result.success:
            return True
        error = result.error.lower() if result.error else ""
        return any(keyword in error for keyword in [
            "已签到", "请勿重复", "重复签到", "already", "签到过", "今日已"
        ])

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        json_data: dict | None = None,
    ) -> dict:
        client = await self._get_client()
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if method.upper() == "GET":
                    resp = await client.get(url, headers=headers)
                else:
                    resp = await client.post(url, headers=headers, json=json_data)
                return resp.json()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    await self._sleep(1)

        raise last_error or Exception(f"Request failed after {self.max_retries} attempts")

    async def _sleep(self, seconds: float):
        import asyncio
        await asyncio.sleep(seconds)

    def _des_encrypt(self, key: bytes, data: bytes) -> bytes:
        padding_len = 8 - (len(data) % 8)
        padded_data = data + (b"\x00" * padding_len)
        key_8 = key[:8].ljust(8, b"\x00")
        cipher = DES.new(key_8, DES.MODE_ECB)
        result = b""
        for i in range(0, len(padded_data), 8):
            block = padded_data[i : i + 8]
            result += cipher.encrypt(block)
        return result

    def _apply_des_rules(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            str_value = str(value) if not isinstance(value, str) else value
            rule = DES_RULE.get(key)

            if rule:
                if rule.get("is_encrypt") == 1:
                    des_key = rule["key"].encode("utf-8")
                    encrypted = self._des_encrypt(des_key, str_value.encode("utf-8"))
                    result[rule["obfuscated_name"]] = base64.b64encode(encrypted).decode()
                else:
                    result[rule["obfuscated_name"]] = value
            else:
                result[key] = value

        return result

    def _get_tn(self, data: dict) -> str:
        sorted_keys = sorted(data.keys())
        result = ""
        for key in sorted_keys:
            value = data[key]
            if isinstance(value, int):
                result += str(value * 10000)
            elif isinstance(value, dict):
                result += self._get_tn(value)
            else:
                result += str(value) if value else ""
        return result

    def _aes_encrypt(self, data: bytes, key: bytes) -> str:
        encoded_b64 = base64.b64encode(data)
        pad_len = 16 - (len(encoded_b64) % 16)
        if pad_len < 16:
            encoded_b64 += b"\x00" * pad_len

        iv = b"0102030405060708"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(encoded_b64, 16)
        encrypted = cipher.encrypt(padded)
        return encrypted.hex()

    def _get_smid(self) -> str:
        time_str = datetime.now().strftime("%Y%m%d%H%M%S")
        uid = str(uuid.uuid4())
        v = f"{time_str}{hashlib.md5(uid.encode()).hexdigest()}00"
        smsk_web = hashlib.md5(f"smsk_web_{v}".encode()).digest()
        suffix = smsk_web[:7].hex()
        return f"{v}{suffix}0"

    async def get_device_id(self) -> str:
        if self._did:
            return self._did

        uid = str(uuid.uuid4())
        pri_id_hash = hashlib.md5(uid.encode()).digest()[:8]
        pri_id_hex = pri_id_hash.hex()

        public_key_der = base64.b64decode(RSA_PUBLIC_KEY)
        rsa_key = RSA.import_key(public_key_der)
        cipher_rsa = PKCS1_v1_5.new(rsa_key)
        encrypted_uid = cipher_rsa.encrypt(uid.encode())
        ep_base64 = base64.b64encode(encrypted_uid).decode()

        in_ms = int(time.time() * 1000)
        browser = dict(BROWSER_ENV)
        browser["vpw"] = str(uuid.uuid4())
        browser["trees"] = str(uuid.uuid4())
        browser["svm"] = in_ms
        browser["pmf"] = in_ms

        des_target = dict(DES_TARGET)
        des_target["smid"] = self._get_smid()
        des_target.update(browser)

        tn_input = self._get_tn(des_target)
        des_target["tn"] = hashlib.md5(tn_input.encode()).hexdigest()

        des_result = self._apply_des_rules(des_target)
        json_str = json.dumps(des_result, separators=(",", ":"))
        compressed = gzip.compress(json_str.encode(), compresslevel=2)

        encrypted = self._aes_encrypt(compressed, pri_id_hex.encode())

        response = await self._request(
            "POST",
            "https://fp-it.portal101.cn/deviceprofile/v4",
            json_data={
                "appId": "default",
                "compress": 2,
                "data": encrypted,
                "encode": 5,
                "ep": ep_base64,
                "organization": "UWXspnCCJN4sfYlNfqps",
                "os": "web",
            },
        )

        if response.get("code") != 1100:
            raise Exception(f"Device ID generation failed: {response}")

        self._did = f"B{response['detail']['deviceId']}"
        return self._did

    def _generate_signature(
        self, token: str, path: str, body_or_query: str, did: str
    ) -> tuple[str, dict]:
        timestamp = int(time.time()) - 2
        header_ca = {
            "platform": "3",
            "timestamp": str(timestamp),
            "dId": did,
            "vName": "1.0.0",
        }
        header_ca_str = json.dumps(header_ca, separators=(",", ":"))

        s = f"{path}{body_or_query}{timestamp}{header_ca_str}"
        hmac_result = hmac.new(token.encode(), s.encode(), hashlib.sha256).hexdigest()
        sign = hashlib.md5(hmac_result.encode()).hexdigest()

        return sign, header_ca

    def _get_base_headers(self, did: str) -> dict:
        return {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
            "Connection": "close",
            "X-Requested-With": "com.hypergryph.skland",
            "dId": did,
        }

    async def get_authorization(self, user_token: str) -> str:
        did = await self.get_device_id()
        headers = self._get_base_headers(did)

        response = await self._request(
            "POST",
            "https://as.hypergryph.com/user/oauth2/v2/grant",
            headers=headers,
            json_data={"appCode": "4ca99fa6b56cc2ba", "token": user_token, "type": 0},
        )

        if response.get("status") != 0:
            raise Exception(f"Authorization failed: {response.get('message', 'Unknown error')}")

        return response["data"]["code"]

    async def get_credential(self, authorization: str) -> Credential:
        did = await self.get_device_id()
        headers = self._get_base_headers(did)

        response = await self._request(
            "POST",
            "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code",
            headers=headers,
            json_data={"code": authorization, "kind": 1},
        )

        if response.get("code") != 0:
            raise Exception(f"Credential failed: {response.get('message', 'Unknown error')}")

        data = response["data"]
        return Credential(token=data["token"], cred=data["cred"])

    def _get_signed_headers(
        self,
        url: str,
        method: str,
        body: str | None,
        cred: Credential,
        did: str,
    ) -> dict:
        parsed = urlparse(url)
        path = parsed.path
        query = parsed.query or ""

        if method.upper() == "GET":
            sign, header_ca = self._generate_signature(cred.token, path, query, did)
        else:
            sign, header_ca = self._generate_signature(cred.token, path, body or "", did)

        headers = self._get_base_headers(did)
        headers["cred"] = cred.cred
        headers["sign"] = sign
        headers.update({k: str(v) for k, v in header_ca.items()})

        return headers

    async def get_binding_list(self, cred: Credential) -> list[UserBinding]:
        did = await self.get_device_id()
        url = "https://zonai.skland.com/api/v1/game/player/binding"
        headers = self._get_signed_headers(url, "GET", None, cred, did)

        response = await self._request("GET", url, headers=headers)

        if response.get("code") != 0:
            msg = response.get("message", "Unknown error")
            if msg == "用户未登录":
                raise Exception("用户登录已过期，请重新登录")
            raise Exception(f"获取绑定列表失败: {msg}")

        bindings = []
        for item in response.get("data", {}).get("list", []):
            app_code = item.get("appCode", "")
            if app_code not in ("arknights", "endfield"):
                continue

            for binding in item.get("bindingList", []):
                bindings.append(
                    UserBinding(
                        app_code=app_code,
                        game_name=binding.get("gameName", "Unknown"),
                        nickname=binding.get("nickName", "Unknown"),
                        channel_name=binding.get("channelName", "Unknown"),
                        uid=binding.get("uid", ""),
                        game_id=binding.get("gameId", 1),
                        roles=binding.get("roles", []),
                    )
                )

        return bindings

    async def sign_arknights(self, cred: Credential, binding: UserBinding) -> SignInResult:
        did = await self.get_device_id()
        url = "https://zonai.skland.com/api/v1/game/attendance"
        body = json.dumps({"gameId": binding.game_id, "uid": binding.uid}, separators=(",", ":"))
        headers = self._get_signed_headers(url, "POST", body, cred, did)

        response = await self._request(
            "POST",
            url,
            headers=headers,
            json_data={"gameId": binding.game_id, "uid": binding.uid},
        )

        logger.info(f"[明日方舟] {binding.nickname} sign-in response: {json.dumps(response, ensure_ascii=False)}")

        if response.get("code") != 0:
            return SignInResult(
                success=False,
                game="明日方舟",
                nickname=binding.nickname,
                channel=binding.channel_name,
                error=response.get("message", "Unknown error"),
            )

        awards = []
        for award in response.get("data", {}).get("awards", []):
            name = award.get("resource", {}).get("name", "Unknown")
            count = award.get("count", 1)
            awards.append(f"{name}x{count}")

        return SignInResult(
            success=True,
            game="明日方舟",
            nickname=binding.nickname,
            channel=binding.channel_name,
            awards=awards,
        )

    async def sign_endfield(self, cred: Credential, binding: UserBinding) -> list[SignInResult]:
        results = []
        roles = binding.roles

        if not roles:
            return [
                SignInResult(
                    success=False,
                    game="终末地",
                    nickname=binding.nickname,
                    channel=binding.channel_name,
                    error="没有角色数据",
                )
            ]

        did = await self.get_device_id()
        url = "https://zonai.skland.com/web/v1/game/endfield/attendance"

        for role in roles:
            role_nickname = role.get("nickname", binding.nickname)
            role_id = role.get("roleId", "")
            server_id = role.get("serverId", "")

            headers = self._get_signed_headers(url, "POST", "", cred, did)
            headers["Content-Type"] = "application/json"
            headers["sk-game-role"] = f"3_{role_id}_{server_id}"
            headers["referer"] = "https://game.skland.com/"
            headers["origin"] = "https://game.skland.com/"

            client = await self._get_client()
            resp = await client.post(url, headers=headers)
            response = resp.json()

            logger.info(f"[终末地] {role_nickname} sign-in response: {json.dumps(response, ensure_ascii=False)}")

            if response.get("code") != 0:
                results.append(
                    SignInResult(
                        success=False,
                        game="终末地",
                        nickname=role_nickname,
                        channel=binding.channel_name,
                        error=response.get("message", "Unknown error"),
                    )
                )
                continue

            awards = []
            award_ids = response.get("data", {}).get("awardIds", [])
            resource_map = response.get("data", {}).get("resourceInfoMap", {})

            for award in award_ids:
                aid = award.get("id", "")
                if aid in resource_map:
                    info = resource_map[aid]
                    name = info.get("name", "Unknown")
                    count = info.get("count", 1)
                    awards.append(f"{name}x{count}")

            results.append(
                SignInResult(
                    success=True,
                    game="终末地",
                    nickname=role_nickname,
                    channel=binding.channel_name,
                    awards=awards,
                )
            )

        return results

    async def do_full_sign_in(self, user_token: str) -> tuple[list[SignInResult], str]:
        auth_code = await self.get_authorization(user_token)
        cred = await self.get_credential(auth_code)
        bindings = await self.get_binding_list(cred)

        if not bindings:
            return [], ""

        nickname = bindings[0].nickname if bindings else ""
        results = []

        for binding in bindings:
            if binding.app_code == "arknights":
                result = await self.sign_arknights(cred, binding)
                results.append(result)
            elif binding.app_code == "endfield":
                endfield_results = await self.sign_endfield(cred, binding)
                results.extend(endfield_results)

        return results, nickname

    async def check_sign_in_status(self, user_token: str) -> tuple[dict[str, bool], str]:
        try:
            results, nickname = await self.do_full_sign_in(user_token)

            status = {"arknights": False, "endfield": False}

            for r in results:
                if r.game == "明日方舟":
                    status["arknights"] = self._is_signed_today(r)
                elif r.game == "终末地":
                    status["endfield"] = self._is_signed_today(r)

            return status, nickname
        except Exception:
            return {"arknights": False, "endfield": False}, ""

    async def get_ark_card(self, cred: Credential, uid: str) -> Optional[dict]:
        """获取明日方舟角色卡片信息"""
        did = await self.get_device_id()
        url = f"https://zonai.skland.com/api/v1/game/player/info?uid={uid}"
        headers = self._get_signed_headers(url, "GET", None, cred, did)

        try:
            response = await self._request("GET", url, headers=headers)
            if response.get("code") != 0:
                logger.error(f"获取角色卡片失败: {response.get('message')}")
                return None
            return response.get("data")
        except Exception as e:
            logger.error(f"获取角色卡片失败: {e}")
            return None

    async def get_endfield_card(self, cred: Credential, role_id: str, server_id: str, user_id: str) -> Optional[dict]:
        """获取终末地角色卡片信息"""
        did = await self.get_device_id()
        url = f"https://zonai.skland.com/web/v1/game/endfield/card/detail?roleId={role_id}&serverId={server_id}&userId={user_id}"
        headers = self._get_signed_headers(url, "GET", None, cred, did)

        try:
            response = await self._request("GET", url, headers=headers)
            if response.get("code") != 0:
                logger.error(f"获取终末地卡片失败: {response.get('message')}")
                return None
            return response.get("data", {}).get("detail")
        except Exception as e:
            logger.error(f"获取终末地卡片失败: {e}")
            return None

    async def get_rogue_data(self, cred: Credential, uid: str, topic_id: str) -> Optional[dict]:
        """获取肉鸽数据"""
        did = await self.get_device_id()
        url = f"https://zonai.skland.com/api/v1/game/arknights/rogue?uid={uid}&targetUserId={cred.token}&topicId={topic_id}"
        headers = self._get_signed_headers(url, "GET", None, cred, did)

        try:
            response = await self._request("GET", url, headers=headers)
            if response.get("code") != 0:
                logger.error(f"获取肉鸽数据失败: {response.get('message')}")
                return None
            return response.get("data")
        except Exception as e:
            logger.error(f"获取肉鸽数据失败: {e}")
            return None

    async def get_gacha_record(self, uid: str, category: str, size: int = 100) -> Optional[dict]:
        """获取明日方舟抽卡记录（需要额外认证）"""
        return {"error": "抽卡记录功能需要额外配置，请查看文档"}

    async def get_scan(self) -> str:
        """获取扫码登录二维码ID"""
        response = await self._request(
            "POST",
            "https://as.hypergryph.com/general/v1/gen_scan/login",
            json_data={"appCode": "4ca99fa6b56cc2ba"},
        )
        if response.get("status") != 0:
            raise Exception(f"获取二维码失败: {response.get('msg')}")
        return response["data"]["scanId"]

    async def get_scan_status(self, scan_id: str) -> Optional[str]:
        """检查扫码状态"""
        client = await self._get_client()
        response = await client.get(
            "https://as.hypergryph.com/general/v1/scan_status",
            params={"scanId": scan_id},
        )
        data = response.json()
        if data.get("status") != 0:
            return None
        return data["data"].get("scanCode")

    async def get_token_by_scan_code(self, scan_code: str) -> str:
        """通过扫码获取token"""
        response = await self._request(
            "POST",
            "https://as.hypergryph.com/user/auth/v1/token_by_scan_code",
            json_data={"scanCode": scan_code},
        )
        if response.get("status") != 0:
            raise Exception(f"获取token失败: {response.get('msg')}")
        return response["data"]["token"]

    async def get_grant_code(self, token: str, token_type: int = 0) -> str:
        """获取授权码"""
        response = await self._request(
            "POST",
            "https://as.hypergryph.com/user/oauth2/v2/grant",
            headers={"User-Agent": USER_AGENT},
            json_data={"appCode": "4ca99fa6b56cc2ba", "token": token, "type": token_type},
        )
        if response.get("status") != 0:
            raise Exception(f"获取授权码失败: {response.get('message')}")
        return response["data"]["code"]

    async def get_role_token(self, uid: str, grant_code: str) -> str:
        """获取角色Token"""
        response = await self._request(
            "POST",
            "https://arknights.hypergryph.com/api/v1/user/auth/roleToken",
            headers={"User-Agent": USER_AGENT},
            json_data={"code": grant_code, "uid": uid},
        )
        if response.get("code") != 0:
            raise Exception(f"获取角色Token失败: {response.get('message')}")
        return response["data"]["roleToken"]

    async def get_ak_cookie(self, role_token: str) -> str:
        """获取明日方舟Cookie"""
        client = await self._get_client()
        response = await client.get(
            "https://arknights.hypergryph.com/api/v1/user/setting",
            headers={
                "User-Agent": USER_AGENT,
                "X-Role-Token": role_token,
            },
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                return data["data"]["cookie"]
        return ""

    async def get_gacha_categories(self, uid: str, role_token: str, access_token: str, ak_cookie: str) -> list:
        """获取抽卡类别"""
        url = f"https://ak.hypergryph.com/user/api/inquiry/gacha/cate?uid={uid}"
        client = await self._get_client()
        response = await client.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "X-Account-Token": access_token,
                "X-Role-Token": role_token,
            },
            cookies={"ak-user-center": ak_cookie} if ak_cookie else {},
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", [])
        return []

    async def get_gacha_history(
        self,
        uid: str,
        role_token: str,
        access_token: str,
        ak_cookie: str,
        category: str,
        size: int = 100,
        gacha_ts: str = None,
        pos: int = None,
    ) -> Optional[dict]:
        """获取抽卡历史记录"""
        url = "https://ak.hypergryph.com/user/api/inquiry/gacha/history"
        params = {
            "uid": uid,
            "category": category,
            "size": size,
        }
        if gacha_ts:
            params["gachaTs"] = gacha_ts
        if pos is not None:
            params["pos"] = pos

        client = await self._get_client()
        response = await client.get(
            url,
            params=params,
            headers={
                "User-Agent": USER_AGENT,
                "X-Account-Token": access_token,
                "X-Role-Token": role_token,
            },
            cookies={"ak-user-center": ak_cookie} if ak_cookie else {},
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", {})
        return None

    async def get_all_gacha_records(self, uid: str, role_token: str, access_token: str, ak_cookie: str, category: str):
        """获取所有抽卡记录（自动分页）"""
        all_records = []
        page = await self.get_gacha_history(uid, role_token, access_token, ak_cookie, category)
        if not page:
            return all_records

        prev_ts = None
        prev_pos = None
        while page:
            gacha_list = page.get("gachaList") or page.get("list", [])
            if not gacha_list:
                break
            all_records.extend(gacha_list)
            if not page.get("hasMore"):
                break
            next_ts = str(page.get("nextTs") or page.get("gachaTs") or "")
            next_pos = page.get("nextPos") or page.get("pos")
            if (next_ts, next_pos) == (prev_ts, prev_pos):
                break
            prev_ts, prev_pos = next_ts, next_pos
            page = await self.get_gacha_history(
                uid, role_token, access_token, ak_cookie, category,
                gachaTs=next_ts or None, pos=next_pos
            )
        return all_records