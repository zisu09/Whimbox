import whimbox.task.daily_task as daily_task
from whimbox.common.scripts_manager import scripts_manager
from whimbox.task.navigation_task.auto_path_task import AutoPathTask
from whimbox.task.navigation_task.record_path_task import RecordPathTask
from whimbox.task.photo_task.daily_photo_task import DailyPhotoTask
from whimbox.task.macro_task.record_macro_task import RecordMacroTask
from whimbox.task.macro_task.run_macro_task import RunMacroTask
from whimbox.task.daily_task.xinghai_task import XinghaiTask
from whimbox.task.mira_crown_task.mira_crown_task import MiraCrownTask
from whimbox.task.daily_task.xinghai_run_task import XinghaiRunTask
from whimbox.task.task_template import STATE_TYPE_SUCCESS, STATE_TYPE_ERROR
from whimbox.common.logger import logger
from whimbox.common.cvars import MCP_CONFIG
from whimbox.common.handle_lib import HANDLE_OBJ
from whimbox.common.notification import send_notification

import socket
import functools
from fastmcp import FastMCP
from starlette.responses import JSONResponse

def windows_notify(func):
    """
    Windows 通知装饰器
    在方法执行后，将返回结果中的 message 通过 Windows 通知显示
    """
    @functools.wraps(func)
    async def wrapper(**kwargs):
        result = await func(**kwargs)
        
        # 提取并发送通知
        if isinstance(result, dict) and 'message' in result:
            message = result.get('message', '')
            status = result.get('status', '')
            
            # 根据状态设置标题
            if status == STATE_TYPE_SUCCESS:
                title = "奇想盒 - 任务完成"
            else:
                title = "奇想盒 - 任务失败"
            
            # 发送通知
            try:
                send_notification(title=title, message=message, status=status)
            except Exception as e:
                logger.debug(f"发送通知失败（不影响主功能）: {e}")
        
        return result
    return wrapper


def check_game_ok(func):
    @functools.wraps(func)
    async def wrapper(**kwargs):
        if not HANDLE_OBJ.is_alive():
            return {
                "status": STATE_TYPE_ERROR,
                "message": "游戏未启动，请先启动游戏"
            }
        shape_ok, width, height = HANDLE_OBJ.check_shape()
        if not shape_ok:
            return {
                "status": STATE_TYPE_ERROR,
                "message": "奇想盒只支持16:9与16:10的游戏分辨率"
            }
        logger.info(f"游戏分辨率：{width}x{height}")
        if width > 2560 or width < 1920:
            from whimbox.ingame_ui.ingame_ui import win_ingame_ui
            msg = f"❗当前游戏分辨率：{width}x{height}。推荐分辨率为：1920x1080或1920x1200或2560x1440或2560x1600。如遇到bug，请修改游戏分辨率后重试\n"
            if win_ingame_ui:
                win_ingame_ui.update_message(msg, "update_ai_message")
            logger.info(msg)
        return await func(**kwargs)
    return wrapper

mcp = FastMCP('whimbox_server')


@mcp.tool()
@check_game_ok
async def jihua_task(target_material=None, cost_material=None) -> dict:
    """
    素材激化：消耗活跃能量，用大世界材料换取噗灵、丝线、闪亮泡泡

    Args:
        target_material: 可选，用于兑换的材料名，只支持噗灵、丝线、闪亮泡泡。如果不输入，会自动读取配置文件
        cost_material: 可选，用于消耗材料名。如果不输入，会自动读取配置文件

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    jihua_task = daily_task.JihuaTask(target_material, cost_material)
    task_result = jihua_task.task_run()
    return task_result.to_dict()


@mcp.tool()
@check_game_ok
async def bless_task(level_name=None) -> dict:
    """
    消耗活跃能量，获取祝福闪光

    Args:
        level_name: 可选，要挑战的祝福闪光幻境的关卡名，如果不输入，会自动读取配置文件

    Returns:
        dict: 包含操作状态的字典，包含status和message字段

    Example:
        (level_name=巨蛇遗迹试炼)
    """
    bless_task = daily_task.BlessTask(level_name)
    task_result = bless_task.task_run()
    return task_result.to_dict()


@mcp.tool()
@check_game_ok
async def monster_task(level_name=None) -> dict:
    """
    消耗活跃能量，挑战魔物试炼幻境

    Args:
        level_name: 可选，要挑战的魔物试炼幻境的关卡名，如果不输入，会自动读取配置文件

    Returns:
        dict: 包含操作状态的字典，包含status和message字段

    Example:
        (level_name=能量)
        (level_name=抛掷)
    """
    if len(level_name) > 2:
        return {
            "status": STATE_TYPE_ERROR,
            "message": "魔物试炼幻境的关卡名，只需要输入最后两个字"
        }
    monster_task = daily_task.MonsterTask(level_name)
    task_result = monster_task.task_run()
    return task_result.to_dict()


@mcp.tool()
@check_game_ok
async def dig_task() -> dict:
    """
    美鸭梨挖掘，只有当明确说明“挖掘”或“美鸭梨挖掘”时才能调用这个工具

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    dig_task = daily_task.DigTaskV2()
    task_result = dig_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def zhaoxi_task() -> dict:
    """
    检查每日任务（朝夕心愿）的进度

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    zhaoxi_task = daily_task.ZhaoxiTask()
    task_result = zhaoxi_task.task_run()
    return task_result.to_dict()


@mcp.tool()
@check_game_ok
async def navigation_task(target=None, type=None, count=None) -> dict:
    """
    指定素材名，或素材获取方法，进行获取。还可以指定要获取的数量

    Args:
        target: 可选，要获取的素材名
        type: 可选，素材获取方法，只能输入“采集”、“捕虫”、“钓鱼”、“清洁”
        count: 可选，要获取的素材数量

    Returns:
        dict: 包含操作状态的字典，包含status和message字段

    Example:
        (target=星荧草),
        (type=采集)
        (target=发卡蚱蜢, count=1)
        (type=钓鱼, count=3)
    """
    path_record = scripts_manager.query_path(target=target, type=type, count=count, return_one=True)
    if path_record is None:
        return {
            "status": STATE_TYPE_ERROR,
            "message": f"没有符合要求的跑图路线"
        }
    else:
        task = AutoPathTask(path_record=path_record, excepted_num=count)
        task_result = task.task_run()
        return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def load_path(path_name: str) -> dict:
    """
    加载并测试指定的跑图路径文件

    Args:
        path_name: 路径文件名

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    path_record = scripts_manager.query_path(path_name=path_name, return_one=True)
    if path_record is None:
        return {
            "status": STATE_TYPE_ERROR,
            "message": f"路线{path_name}不存在"
        }
    else:
        task = AutoPathTask(path_record=path_record)
        task_result = task.task_run()
        return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def record_path() -> dict:
    """
    记录跑图路线

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    task = RecordPathTask()
    task_result = task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def record_macro() -> dict:
    """
    录制宏
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    record_macro_task = RecordMacroTask()
    task_result = record_macro_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def run_macro(macro_name: str) -> dict:
    """
    运行宏
    Args:
        macro_filename: 宏名称
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    macro_record = scripts_manager.query_macro(macro_name, is_play_music=False, return_one=True)
    if macro_record is None:
        return {
            "status": STATE_TYPE_ERROR,
            "message": f"宏\"{macro_name}\"不存在"
        }
    run_macro_task = RunMacroTask(macro_record.info.name)
    task_result = run_macro_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def play_music(macro_name: str) -> dict:
    """
    演奏音乐
    Args:
        macro_name: 乐谱名称
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    macro_record = scripts_manager.query_macro(macro_name, is_play_music=True, return_one=True)
    if macro_record is None:
        return {
            "status": STATE_TYPE_ERROR,
            "message": f"乐谱\"{macro_name}\"不存在"
        }
    run_macro_task = RunMacroTask(macro_record.info.name)
    task_result = run_macro_task.task_run()
    return task_result.to_dict()


@mcp.tool()
async def open_path_folder() -> dict:
    """
    打开路线文件夹
    """
    res, msg = scripts_manager.open_path_folder()
    return {
        "status": STATE_TYPE_SUCCESS if res else STATE_TYPE_ERROR,
        "message": msg
    }

@mcp.tool()
@check_game_ok
async def daily_photo_task() -> dict:
    """
    简单拍照，用于完成每日任务

    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    daily_photo_task = DailyPhotoTask()
    task_result = daily_photo_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@windows_notify
async def all_in_one_task() -> dict:
    """
    一条龙，一次性完成所有任务。无论结果如何，只调用一次。
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    all_in_one_task = daily_task.AllInOneTask()
    task_result = all_in_one_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def monthly_pass_task() -> dict:
    """
    领取奇迹之旅（大月卡）奖励
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    monthly_pass_task = daily_task.MonthlyPassTask()
    task_result = monthly_pass_task.task_run()
    return task_result.to_dict()


@mcp.tool()
@check_game_ok
async def weekly_realm_task() -> dict:
    """
    每周幻境，周本，心之突破幻境
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    weekly_realm_task = daily_task.WeeklyRealmTask()
    task_result = weekly_realm_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def xinghai_task() -> dict:
    """
    星海日常任务一条龙
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    xinghai_task = XinghaiTask()
    task_result = xinghai_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def mira_crown_task() -> dict:
    """
    奇迹之冠搭配赛，奇迹之冠巅峰赛
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    mira_crown_task = MiraCrownTask(force_start=True)
    task_result = mira_crown_task.task_run()
    return task_result.to_dict()

@mcp.tool()
@check_game_ok
async def xinghai_run_task() -> dict:
    """
    收集星光结晶
    Returns:
        dict: 包含操作状态的字典，包含status和message字段
    """
    xinghai_run_task = XinghaiRunTask()
    task_result = xinghai_run_task.task_run()
    return task_result.to_dict()


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """
    检查MCP服务器是否健康
    """
    return JSONResponse({"status": "healthy", "service": "mcp-server"})

def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True

def get_available_port(max_attempts: int = 100) -> int:
    port = MCP_CONFIG["port"]
    host = '0.0.0.0'
    for _ in range(max_attempts):
        if not is_port_in_use(port, host):
            MCP_CONFIG["port"] = port
            logger.debug(f"MCP服务器使用端口 {port}")
            return port
        logger.debug(f"MCP服务器端口 {port} 已被占用，尝试下一个端口")
        port += 1
    return None

def start_mcp_server():
    logger.debug("开始初始化MCP服务器")
    port = get_available_port()
    if port:
        mcp.run(
            show_banner=False,
            transport="streamable-http",
            host='0.0.0.0',
            port=MCP_CONFIG["port"],
        )
    