"""本地网络边界校验：拒绝一切非私有网段/非 localhost 的服务端地址.

隐私约束：本项目只用于连接自建局域网 xiaozhi-esp32-server 做数据采集，
任何解析结果落在私有网段之外（域名、公网 IP）都必须硬性拒绝，不是可配置项。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
)


class UntrustedEndpointError(RuntimeError):
    """目标地址不在允许的私有网段/localhost 范围内."""


def assert_private_or_localhost(url: str, *, label: str = "地址") -> None:
    """校验 URL 的主机名必须是 localhost 或私有网段 IP，否则抛异常.

    Args:
        url: 待校验的完整 URL（如 OTA 地址或 WebSocket 地址）。
        label: 报错信息里的标签，便于区分是哪一步校验失败。

    Raises:
        UntrustedEndpointError: 主机名为空、是域名、或不在私有网段/loopback 内。
    """
    host = urlparse(url).hostname
    if not host:
        raise UntrustedEndpointError(f"{label}无法解析出主机名: {url!r}")

    if host.lower() == "localhost":
        return

    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise UntrustedEndpointError(
            f"{label}被拒绝: 主机名 {host!r} 不是 IP 地址（域名一律禁止），"
            f"本项目只允许连接私有网段 IP 或 localhost（url={url!r}）"
        ) from exc

    if not any(ip in net for net in _ALLOWED_NETWORKS):
        raise UntrustedEndpointError(
            f"{label}被拒绝: {host} 不属于私有网段 "
            f"(10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8) 或 localhost，"
            f"本项目禁止连接非局域网地址（url={url!r}）"
        )
