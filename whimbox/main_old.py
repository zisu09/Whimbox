import os
import sys

from whimbox.common.logger import logger
from whimbox.common.path_lib import SCRIPT_PATH


def init():
    """
    如果更新后有什么初始化或者变更操作，就写在这里
    启动器会在更新后调用whimbox init命令
    """
    logger.info("正在初始化应用程序环境...")
    from whimbox.config.config import GlobalConfig
    GlobalConfig()
    if not os.path.exists(SCRIPT_PATH):
        os.makedirs(SCRIPT_PATH, exist_ok=True)
    logger.info("初始化完成")

def _prepare_env():
    """运行前环境准备"""
    from whimbox.common.utils.utils import is_admin
    if not is_admin():
        logger.error("请用管理员权限运行")
        exit()

    from importlib.metadata import PackageNotFoundError, version
    try:
        logger.info(f"奇想盒版本号: {version('whimbox')}")
    except PackageNotFoundError:
        logger.info(f"奇想盒版本号: dev")

    if not os.path.exists(SCRIPT_PATH):
        os.makedirs(SCRIPT_PATH, exist_ok=True)

    # from whimbox.common.handle_lib import HANDLE_OBJ
    # import time
    # logger.info("WAIT_FOR_GAME_START")
    # while not HANDLE_OBJ.get_handle():
    #     time.sleep(5)
    #     HANDLE_OBJ.refresh_handle()
    # logger.info("GAME_STARTED")

def run_app():
    """运行主应用程序"""
    _prepare_env()

    import asyncio
    import threading

    from whimbox.mcp_agent import mcp_agent
    from whimbox.mcp_server import start_mcp_server
    from whimbox.plugin_runtime import init_plugins

    init_plugins()

    mcp_thread = threading.Thread(target=start_mcp_server)
    mcp_thread.daemon = True
    mcp_thread.start()
    asyncio.run(mcp_agent.start())

    from whimbox.ingame_ui.ingame_ui import run_ingame_ui
    run_ingame_ui()

def run_one_dragon():
    """直接运行一条龙任务，完成后退出"""
    _prepare_env()

    from whimbox.task.daily_task.all_in_one_task import AllInOneTask
    logger.info("开始执行一条龙任务...")
    task = AllInOneTask()
    task_result = task.task_run()
    logger.info(f"一条龙任务完成: {task_result.message}")
    logger.info("任务结束，程序退出")

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "init":
            init()
        elif sys.argv[1] == "startOneDragon":
            run_one_dragon()
        else:
            run_app()
    else:
        run_app()

if __name__ == "__main__":
    main()