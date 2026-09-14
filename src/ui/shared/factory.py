"""按 mode 创建界面实现（返回 ViewPort）."""

from typing import TYPE_CHECKING, Optional

from src.logging import get_logger

if TYPE_CHECKING:
    from src.core.event_bus import EventBus
    from src.core.task_manager import TaskManager
    from src.ui.shared.viewport import ViewPort

logger = get_logger()


def create_viewport(
    mode: str,
    event_bus: "EventBus",
    task_manager: Optional["TaskManager"] = None,
) -> "ViewPort":
    """gui / cli / tui."""
    normalized = (mode or "cli").lower()

    if normalized == "gui":
        from src.ui.gui import GuiViewManager

        logger.debug("create_viewport: gui")
        return GuiViewManager(event_bus=event_bus, task_manager=task_manager)

    if normalized == "tui":
        from src.ui.tui import TuiViewManager

        logger.info("create_viewport: tui")
        return TuiViewManager(event_bus=event_bus, task_manager=task_manager)

    if normalized != "cli":
        logger.warning(f"未知 UI 模式 {mode!r}，回退 cli")

    from src.ui.cli import CliViewManager

    logger.info("create_viewport: cli")
    return CliViewManager(event_bus=event_bus, task_manager=task_manager)
