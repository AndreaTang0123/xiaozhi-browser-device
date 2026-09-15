"""环境变量 / .env 加载与强制校验.

本项目只允许连接自建局域网 xiaozhi-esp32-server，服务端地址一律通过环境变量
（或项目根目录 .env 文件）提供，不在源码里保留任何默认值/官方地址兜底。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class MissingEnvError(RuntimeError):
    """必需的环境变量缺失."""


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    if not key:
        return None
    return key, value


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """加载 .env 文件到 os.environ（已存在的环境变量优先，不覆盖）.

    默认在项目根目录（本文件上两级）查找 .env；找不到则静默跳过——
    这不是错误，因为变量也可能已经通过真实环境变量设置。
    """
    path = dotenv_path or (Path(__file__).resolve().parents[2] / ".env")
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if not parsed:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    """读取必需的环境变量；缺失或为空时立即抛出异常（fail fast，不兜底）."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingEnvError(
            f"必需的环境变量 {name} 未设置或为空。"
            f"请复制 .env.example 为 .env 并填入你自建 xiaozhi-esp32-server 的真实地址，"
            f"本项目不允许回退到任何默认/公网地址。"
        )
    return value


def optional_env(name: str, default: str = "") -> str:
    """读取可选环境变量；未设置时返回 default（不是公网地址，仅用于非连接类配置）."""
    return os.environ.get(name, default).strip()
