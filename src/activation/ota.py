"""OTA 配置拉取与本地配置初始化."""

from __future__ import annotations

import asyncio
import socket
import ssl
from typing import TYPE_CHECKING, Dict, Optional

import aiohttp

from src.constants.system import SystemConstants
from src.logging import get_logger
from src.utils.network_guard import assert_private_or_localhost

if TYPE_CHECKING:
    from src.activation.identity import DeviceIdentity
    from src.utils.config_manager import ConfigManager

logger = get_logger()


class OtaConfigClient:
    """拉取 OTA 配置并写回 ConfigManager."""

    def __init__(
        self,
        config_manager: "ConfigManager",
        identity: "DeviceIdentity",
    ) -> None:
        self._config = config_manager
        self._identity = identity
        self._local_ip: Optional[str] = None
        # 解析结果
        self.activation_data: Optional[Dict] = None
        self.server_activated: bool = False

    async def ensure_local_ip(self) -> str:
        try:
            loop = asyncio.get_running_loop()
            self._local_ip = await loop.run_in_executor(None, self._sync_get_ip)
        except Exception:
            self._local_ip = "127.0.0.1"
        return self._local_ip

    def initialize_config(self) -> None:
        self._config.initialize_client_id()
        device_id = self._config.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        if not device_id:
            mac = self._identity.get_mac_address()
            if mac:
                self._config.update_config("SYSTEM_OPTIONS.DEVICE_ID", mac)
                logger.info(f"已设置DEVICE_ID: {mac}")
        logger.info(
            f"CLIENT_ID: {self._config.get_config('SYSTEM_OPTIONS.CLIENT_ID')}"
        )
        logger.info(
            f"DEVICE_ID: {self._config.get_config('SYSTEM_OPTIONS.DEVICE_ID')}"
        )

    async def fetch_ota_config(self) -> Dict:
        ota_url = self._config.get_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL")
        device_id = self._config.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        if not ota_url:
            raise ValueError(
                "OTA_VERSION_URL 未配置：请设置环境变量 XIAOZHI_OTA_URL "
                "（见 .env.example），本项目不允许回退到任何默认地址"
            )
        if not device_id:
            raise ValueError("DEVICE_ID 未配置")

        # 隐私约束：OTA 地址必须是私有网段/localhost，域名和公网 IP 一律拒绝
        assert_private_or_localhost(ota_url, label="OTA 地址")

        headers = self._build_ota_headers()
        payload = self._build_ota_payload()
        logger.info(f"[1/3] OTA 请求地址: {ota_url}")

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            async with session.post(ota_url, headers=headers, json=payload) as response:
                if response.status != 200:
                    raise ValueError(f"OTA服务器返回错误: {response.status}")
                data = await response.json()
                self._process_ota_response(data)
                return data

    def _build_ota_headers(self) -> Dict:
        headers = {
            "Device-Id": self._config.get_config("SYSTEM_OPTIONS.DEVICE_ID"),
            "Client-Id": self._config.get_config("SYSTEM_OPTIONS.CLIENT_ID"),
            "Content-Type": "application/json",
            "User-Agent": (
                f"{SystemConstants.BOARD_TYPE}/"
                f"{SystemConstants.APP_NAME}-{SystemConstants.APP_VERSION}"
            ),
            "Accept-Language": "zh-CN",
        }
        activation_version = self._config.get_config(
            "SYSTEM_OPTIONS.NETWORK.ACTIVATION_VERSION", "v1"
        )
        if activation_version == "v2":
            headers["Activation-Version"] = SystemConstants.APP_VERSION
        return headers

    def _build_ota_payload(self) -> Dict:
        hmac_key = self._identity.load_efuse_data().get("hmac_key", "unknown")
        return {
            "application": {
                "version": SystemConstants.APP_VERSION,
                "elf_sha256": hmac_key,
            },
            "board": {
                "type": SystemConstants.BOARD_TYPE,
                "name": SystemConstants.APP_NAME,
                "ip": self._local_ip,
                "mac": self._config.get_config("SYSTEM_OPTIONS.DEVICE_ID"),
            },
        }

    def _process_ota_response(self, data: Dict) -> None:
        updates: Dict[str, object] = {}
        if "mqtt" in data and data["mqtt"]:
            updates["SYSTEM_OPTIONS.NETWORK.MQTT_INFO"] = data["mqtt"]
            logger.info("MQTT配置已更新")
        if "websocket" in data:
            ws = data["websocket"]
            if ws.get("url"):
                # 隐私约束：OTA 下发的 websocket 地址同样必须是私有网段/localhost
                assert_private_or_localhost(ws["url"], label="OTA 返回的 WebSocket 地址")
                updates["SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL"] = ws["url"]
                logger.info(f"[2/3] OTA 返回的 WebSocket 地址: {ws['url']}")
            token = ws.get("token", "test-token") or "test-token"
            updates["SYSTEM_OPTIONS.NETWORK.WEBSOCKET_ACCESS_TOKEN"] = token
        if updates:
            self._config.update_configs(updates)
        if "activation" in data:
            logger.info("检测到激活数据，设备需要激活")
            self.activation_data = data["activation"]
            self.server_activated = False
        else:
            # 自建 server 的 OTA 响应通常不带 activation 字段（无网页控制台/无需人工激活码）；
            # 这不是代码在"默默绕过"激活流程，而是协议约定：无 activation 数据即视为已授权。
            logger.info(
                "OTA 响应无 activation 字段，视为服务端已授权（跳过激活码流程，"
                "如需强制走激活 UI 请让自建 server 在 OTA 响应里带上 activation.code/challenge）"
            )
            self.activation_data = None
            self.server_activated = True

    def _sync_get_ip(self) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
