import argparse
import asyncio
import locale
import os
import signal
import sys

# Windows: 强制 C/C++ 运行时使用 UTF-8，解决 sherpa-onnx 读取声调拼音文件乱码
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        locale.setlocale(locale.LC_ALL, ".UTF-8")
    except locale.Error:
        pass

os.environ["QSG_RHI_BACKEND"] = "opengl"
# 强制 qasync 使用 PySide6
os.environ["QT_API"] = "pyside6"
# 使用 Basic 样式以支持自定义控件
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"


def parse_args():
    """解析命令行参数."""
    from src.constants.system import SystemConstants

    parser = argparse.ArgumentParser(description=SystemConstants.APP_DISPLAY_NAME)
    # 运行模式选择
    # - gui: 图形界面模式，使用 PySide6 + QML
    # - cli: 命令行模式，使用终端交互（轻量，适合无屏/SSH）
    # - tui: 全屏 TUI（Textual），可编辑配置；需 uv sync --extra tui
    parser.add_argument(
        "--mode",
        choices=["gui", "cli", "tui"],
        default="gui",
        help="运行模式（默认 gui）：gui / cli / tui(全屏终端)",
    )
    parser.add_argument(
        "--protocol",
        choices=["websocket"],
        default="websocket",
        metavar="PROTOCOL",
        help="通信协议：websocket（唯一支持的协议）",
    )
    parser.add_argument(
        "--skip-activation",
        action="store_true",
        help="跳过激活流程，直接启动应用（仅用于调试）",
    )
    return parser.parse_args()


# 先解析参数，再初始化配置与日志（禁止 ConfigManager 懒单例）
_args = parse_args()

from src.utils.config_manager import initialize_config  # noqa: E402

initialize_config()

from src.logging import load_logging_config, setup_logging  # noqa: E402

# CLI/TUI 模式禁用控制台日志输出（由界面接管）
setup_logging(
    enable_console=(_args.mode not in ("cli", "tui")),
    config=load_logging_config(),
)

from src.bootstrap.container import ServiceContainer  # noqa: E402
from src.constants.system import SystemConstants  # noqa: E402
from src.logging import get_logger  # noqa: E402
from src.utils.config_manager import get_config  # noqa: E402
from src.utils.env_config import load_dotenv, optional_env, require_env  # noqa: E402

logger = get_logger()


def _apply_env_overrides() -> None:
    """从 .env / 环境变量强制写入服务端地址，缺失即 fail fast，绝不回退默认地址."""
    load_dotenv()
    ota_url = require_env("XIAOZHI_OTA_URL")

    config = get_config()
    config.update_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL", ota_url, save=False)

    activation_version = optional_env("XIAOZHI_ACTIVATION_VERSION")
    if activation_version:
        config.update_config(
            "SYSTEM_OPTIONS.NETWORK.ACTIVATION_VERSION", activation_version, save=False
        )

    authorization_url = optional_env("XIAOZHI_AUTHORIZATION_URL")
    if authorization_url:
        config.update_config(
            "SYSTEM_OPTIONS.NETWORK.AUTHORIZATION_URL", authorization_url, save=False
        )

    config.save_config()
    logger.info(f"已从环境变量加载 OTA_VERSION_URL: {ota_url}")


_apply_env_overrides()


async def handle_activation(mode: str) -> bool:
    """处理设备激活流程.

    Args:
        mode: 运行模式，"gui"、"cli" 或 "tui"

    Returns:
        bool: 激活是否成功
    """
    try:
        from src.activation import ActivationService, create_activation_ui

        logger.info("开始设备激活流程检查...")
        activation_service = await ActivationService.create()
        init_result = await activation_service.initialize()

        if not init_result.get("success", False):
            logger.error(f"初始化失败: {init_result.get('error', '未知错误')}")
            return False

        if not init_result.get("need_activation_ui", False):
            logger.info("设备已激活，无需激活流程")
            return True

        ui = create_activation_ui(mode, activation_service, init_result)
        return await ui.run()

    except Exception as e:
        logger.error(f"激活流程异常: {e}", exc_info=True)
        return False


async def start_app(mode: str, protocol: str, skip_activation: bool) -> int:
    """启动应用的统一入口."""
    global _container  # 用于 SIGINT 处理
    logger.info(f"启动{SystemConstants.APP_DISPLAY_NAME}")

    # 处理激活流程
    if not skip_activation:
        activation_success = await handle_activation(mode)
        if not activation_success:
            logger.error("设备激活失败，程序退出")
            return 1
    else:
        logger.warning("跳过激活流程（调试模式）")

    # 创建并启动应用程序
    _container = ServiceContainer()
    return await _container.run(mode=mode, protocol=protocol)


# 全局容器引用，用于 SIGINT 处理
_container = None


if __name__ == "__main__":
    exit_code = 1
    try:
        # 使用已解析的参数
        args = _args

        # 检测Wayland环境并设置Qt平台插件配置
        import os

        is_wayland = (
            os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        if args.mode == "gui" and is_wayland:
            if "QT_QPA_PLATFORM" not in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
                logger.info("Wayland环境：设置QT_QPA_PLATFORM=wayland;xcb")
            os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
            logger.info("Wayland环境检测完成，已应用兼容性配置")

        # 信号处理
        try:
            if hasattr(signal, "SIGTRAP"):
                signal.signal(signal.SIGTRAP, signal.SIG_IGN)
        except Exception:
            pass

        if args.mode == "gui":
            # GUI 模式：使用 PySide6 + qasync
            try:
                import qasync
                from PySide6.QtWidgets import QApplication
            except ImportError as e:
                logger.error(
                    "GUI 模式需要 PySide6 + qasync，当前环境未安装。\n"
                    "请用项目 venv 安装 GUI 依赖后重试：\n"
                    "  uv sync --extra gui\n"
                    "  # 或: pip install '.[gui]'\n"
                    "然后：\n"
                    "  uv run python main.py\n"
                    "  # 或: .venv/bin/python main.py\n"
                    "不要 GUI 时可用：\n"
                    "  python main.py --mode cli\n"
                    "  python main.py --mode tui   # 需 uv sync --extra tui\n"
                    f"(原始错误: {e})"
                )
                sys.exit(1)

            qt_app = QApplication.instance() or QApplication(sys.argv)
            qt_app.setQuitOnLastWindowClosed(False)

            loop = qasync.QEventLoop(qt_app)
            asyncio.set_event_loop(loop)
            logger.info("已创建 PySide6 + qasync 事件循环")

            # 设置 SIGINT 信号处理 - 通过 TaskManager 请求关闭
            shutdown_state = {"requested": False}

            def handle_sigint(*_):
                if shutdown_state["requested"]:
                    return
                shutdown_state["requested"] = True
                logger.info("收到 SIGINT 信号，正在退出...")

                # 通过 TaskManager 请求优雅关闭
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                    else:
                        # 容器未就绪，直接退出 Qt
                        if loop.is_running():
                            loop.call_soon_threadsafe(qt_app.quit)
                except Exception:
                    qt_app.quit()

            signal.signal(signal.SIGINT, handle_sigint)

            try:
                with loop:
                    exit_code = loop.run_until_complete(
                        start_app(args.mode, args.protocol, args.skip_activation)
                    )
            except RuntimeError as e:
                # 捕获 qasync 的 "Event loop stopped before Future completed" 错误
                if "Event loop stopped before Future completed" in str(e):
                    logger.debug("事件循环已正常终止")
                    exit_code = 0
                else:
                    raise
        else:
            # CLI / TUI：标准 asyncio
            if args.mode == "tui":
                try:
                    import textual  # noqa: F401
                except ImportError as e:
                    logger.error(
                        "TUI 模式需要 textual。请运行:\n"
                        "  uv sync --extra tui\n"
                        "  pip install '.[tui]'\n"
                        "无屏/SSH 请继续用: python main.py --mode cli\n"
                        f"(原始错误: {e})"
                    )
                    sys.exit(1)

            # CLI 模式：标准 asyncio；SIGINT 请求 TaskManager 关闭
            shutdown_state = {"requested": False}

            def handle_sigint_cli(*_):
                if shutdown_state["requested"]:
                    # 二次 Ctrl+C：硬退
                    logger.warning("再次收到 SIGINT，强制退出")
                    os._exit(130)
                shutdown_state["requested"] = True
                logger.info("收到 SIGINT 信号，正在退出...")
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                except Exception:
                    pass

            signal.signal(signal.SIGINT, handle_sigint_cli)
            exit_code = asyncio.run(
                start_app(args.mode, args.protocol, args.skip_activation)
            )

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        exit_code = 0
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
        exit_code = 1
    finally:
        sys.exit(exit_code)
