"""MCP 插件.

管理 MCP 工具和消息处理。McpServer 必须由容器注入。
"""

from typing import TYPE_CHECKING, Any, Optional

from src.logging import get_logger
from src.mcp.mcp_server import McpServer
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


class McpPlugin(Plugin):
    name = "mcp"
    priority = 20  # 工具注册，需要较早初始化

    def __init__(self, server: Optional[McpServer] = None) -> None:
        super().__init__()
        if server is None:
            raise ValueError("McpPlugin 需要容器注入的 McpServer")
        self._server: McpServer = server

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        server = self._server

        async def _send(msg: str):
            try:
                await cmd.send_mcp_message(msg)
            except Exception as e:
                logger.error(f"MCP 发送响应失败: {e}", exc_info=True)

        try:
            server.set_send_callback(_send)
            # 摄像头：懒创建一次，挂到 server，供 vision 配置与 take_photo 共用
            from src.mcp.tools.camera import create_camera, register_camera_tools
            from src.mcp.tools.screenshot import register_screenshot_tools

            camera = create_camera()
            server.set_camera(camera)
            register_camera_tools(server.add_tool, camera)
            register_screenshot_tools(server.add_tool, camera)

            server.add_common_tools()
        except Exception as e:
            logger.error(f"MCP 工具注册失败: {e}", exc_info=True)

    async def on_incoming_json(self, message: Any) -> None:
        if not isinstance(message, dict):
            return
        try:
            if message.get("type") == "mcp":
                payload = message.get("payload")
                if not payload:
                    return
                await self._server.parse_message(payload)
        except Exception as e:
            logger.error(f"MCP 消息处理失败: {e}", exc_info=True)

    def register_resources(self, pool) -> None:
        async def _mcp_cleanup():
            try:
                self._server.detach()
            except Exception as e:
                logger.debug(f"MCP shutdown 清理失败: {e}", exc_info=True)

        pool.register("mcp.server", _mcp_cleanup)
