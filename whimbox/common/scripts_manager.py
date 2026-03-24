from pydantic import BaseModel
from typing import Optional, Literal
import os
import json

from whimbox.common.path_lib import SCRIPT_PATH
from whimbox.common.logger import logger

# 基础脚本信息
class ScriptInfo(BaseModel):
    name: str
    type: Optional[str] = None
    update_time: Optional[str] = None
    version: Optional[str] = None

# 跑图脚本信息
class PathInfo(ScriptInfo):
    target: Optional[str] = None # 目标：素材名
    count: Optional[int] = None # 目标数量
    region: Optional[str] = None
    map: Optional[str] = None
    test_mode: Optional[bool] = False

# 跑图脚本点位
class PathPoint(BaseModel):
    id: int
    move_mode: str          # 移动模式：行走、跳跃、飞行
    point_type: str      # 点位类型：途径点、必经点
    action: Optional[str] = None
    action_params: Optional[str] = None
    position: list[float]

# 跑图脚本
class PathRecord(BaseModel):
    info: PathInfo
    points: list[PathPoint]

# 宏脚本信息
class MacroInfo(ScriptInfo):
    aspect_ratio: Optional[Literal["16:9", "16:10"]] = None  # 分辨率比例

# 宏脚本步骤
class MacroStep(BaseModel):
    type: Literal["gap", "keyboard", "mouse", "loop", "wait_game_page", "goto_game_page"]  # 操作类型
    key: Optional[str] = None  # 键盘按键名称或鼠标按键名称
    action: Optional[Literal["press", "release"]] = None  # 按键动作：按下/松开
    position: Optional[tuple[int, int]] = None  # 鼠标位置（窗口内坐标，归一化到 width=1920）
    duration: Optional[float] = None  # 间隔时间（秒），仅当 type="gap" 时有效
    loop_count: Optional[int] = None  # 循环次数（仅当 type="loop" 时有效）
    loop_steps: Optional[int] = None  # 循环的步骤数量（仅当 type="loop" 时有效，表示接下来几个步骤需要循环）
    target_game_page: Optional[str] = None  # 等待某个特定游戏页面（仅当 type="wait_game" 时有效）

# 宏脚本
class MacroRecord(BaseModel):
    info: MacroInfo
    steps: list[MacroStep] = []  # 操作步骤列表


class ScriptsManager:

    _instance = None
    _initialized = False
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(ScriptsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.path_dict = {}
        self.macro_dict = {}
        self.init_scripts_dict()

        self._initialized = True

    def init_scripts_dict(self):
        self.path_dict = {}
        self.macro_dict = {}
        # 使用 os.walk 递归遍历所有子文件夹
        for root, dirs, files in os.walk(SCRIPT_PATH):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        try:
                            json_text = f.read()
                            json_dict = json.loads(json_text)
                            if json_dict['info']['type'] == '宏' or json_dict['info']['type'] == '乐谱':
                                macro_record = MacroRecord.model_validate_json(json_text)
                                macro_name = macro_record.info.name
                                if macro_name in self.macro_dict:
                                    if self.macro_dict[macro_name].info.update_time < macro_record.info.update_time:
                                        self.macro_dict[macro_name] = macro_record
                                    else:
                                        continue
                                else:
                                    self.macro_dict[macro_name] = macro_record
                            else:
                                path_record = PathRecord.model_validate_json(json_text)
                                path_name = path_record.info.name
                                if path_name in self.path_dict:
                                    if self.path_dict[path_name].info.update_time < path_record.info.update_time:
                                        self.path_dict[path_name] = path_record
                                    else:
                                        continue
                                else:
                                    self.path_dict[path_name] = path_record
                        except Exception as e:
                            logger.error(f"读取脚本文件{file_path}失败: {e}")
                            continue

    def query_path(self, path_name=None, name=None, target=None, type=None, count=None, return_one=False, show_default=False) -> list[PathRecord] | PathRecord | None:
        # 指定名字就直接返回单文件（用于内部固定路线的任务使用，比如每日任务）
        if path_name:
            return self.path_dict.get(path_name, None)
        
        # 根据要求进行筛选
        res = []
        for _, path_record in self.path_dict.items():
            match = True
            
            if (not show_default) and (
                path_record.info.name.startswith("朝夕心愿_") 
                or path_record.info.name.startswith("星海拾光_")
                or path_record.info.name.startswith("家园日常")):
                match = False

            if name is not None:
                if name.lower() not in path_record.info.name.lower():
                    match = False

            # Filter by target (exact match)
            if target is not None:
                if path_record.info.target != target:
                    match = False
            
            # Filter by type (exact match)
            if type is not None:
                if path_record.info.type != type:
                    match = False
            
            # Filter by count (greater than or equal)
            if count is not None:
                if path_record.info.count is None or path_record.info.count < count:
                    match = False
            
            if match:
                res.append(path_record)
        
        if return_one:
            return res[0] if res else None
        else:
            return res

    def _is_macro_type(self, script_type: Optional[str]) -> bool:
        return script_type in ("宏", "乐谱")

    def _find_script_files_by_name(self, script_name: str, is_macro: bool) -> list[str]:
        """
        递归查找指定名称的脚本文件。

        Args:
            script_name: 脚本名称
            is_macro: True 查找宏/乐谱，False 查找跑图路线
        """
        target_filepaths: list[str] = []
        for root, _, files in os.walk(SCRIPT_PATH):
            for file in files:
                if not file.endswith(".json"):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        script_data = json.load(f)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # 跳过格式错误的文件
                    continue
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    continue

                info = script_data.get("info", {})
                if info.get("name") != script_name:
                    continue

                script_type = info.get("type")
                if is_macro and not self._is_macro_type(script_type):
                    continue
                if not is_macro and self._is_macro_type(script_type):
                    continue
                target_filepaths.append(file_path)

        return target_filepaths
    
    def delete_path(self, path_name: str) -> int:
        """
        删除指定名称的路线
        
        Args:
            path_name: 路线名称
            
        Returns:
            删除的文件数量，如果出错返回 0
        """
        if not path_name:
            logger.warning("Path name is empty, cannot delete")
            return 0
        
        if not os.path.exists(SCRIPT_PATH):
            logger.warning(f"Script path does not exist: {SCRIPT_PATH}")
            return 0
        
        try:
            target_filepath = self._find_script_files_by_name(path_name, is_macro=False)

            # 删除成功后，重新初始化路径字典
            deleted_count = 0
            for file_path in target_filepath:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")
                    continue
            if deleted_count > 0:
                self.init_scripts_dict()
                logger.info(f"Deleted {deleted_count} file(s) for path '{path_name}'")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete path '{path_name}': {e}")
            return 0

    def open_path_folder(self):
        """打开路线文件夹"""
        try:
            if os.path.exists(SCRIPT_PATH):
                os.startfile(SCRIPT_PATH)
                logger.info(f"Opened path folder: {SCRIPT_PATH}")
            else:
                return False, f"路线文件夹不存在:{SCRIPT_PATH}"
        except Exception as e:
            logger.error(f"Failed to open path folder: {e}")
            return False, f"无法打开路线文件夹:{str(e)}"
        return True, f"已打开路线文件夹:{SCRIPT_PATH}"

    def query_macro(self, name=None, is_play_music=False, return_one=False, show_default=False) -> list[MacroRecord] | MacroRecord | None:
        """
        查询宏
        
        Args:
            name: 宏名称，如果提供则返回单个宏，否则返回所有宏的列表（支持模糊匹配）
            
        Returns:
            如果指定name且找到，返回单个MacroRecord；如果name为None，返回匹配的列表
        """
        # 指定名字就直接返回单文件
        if name:
            # 尝试精确匹配
            if name in self.macro_dict:
                if return_one:
                    return self.macro_dict[name]
                else:
                    return [self.macro_dict[name]]
            
            # 模糊匹配
            res = []
            for macro_name, macro_record in self.macro_dict.items():
                if (not show_default) and (
                    macro_record.info.name.startswith("朝夕心愿_") 
                    or macro_record.info.name.startswith("星海拾光_")
                    or macro_record.info.name.startswith("家园日常")):
                    continue
                if name.lower() in macro_name.lower():
                    if macro_record.info.type == "乐谱" and is_play_music:
                        if return_one:
                            return macro_record
                        else:
                            res.append(macro_record)
                    elif macro_record.info.type != "乐谱" and not is_play_music:
                        if return_one:
                            return macro_record
                        else:
                            res.append(macro_record)
            if return_one:
                return res[0] if res else None
            else:
                return res
        
        # 返回所有宏
        res = []
        for _, macro_record in self.macro_dict.items():
            if (not show_default) and (
                macro_record.info.name.startswith("朝夕心愿_") 
                or macro_record.info.name.startswith("星海拾光_")
                or macro_record.info.name.startswith("家园日常")):
                continue
            if macro_record.info.type == "乐谱" and is_play_music:
                if return_one:
                    return macro_record
                else:
                    res.append(macro_record)
            elif macro_record.info.type != "乐谱" and not is_play_music:
                if return_one:
                    return macro_record
                else:
                    res.append(macro_record)
        if return_one:
            return res[0] if res else None
        else:
            return res
    
    def delete_macro(self, macro_name: str) -> int:
        """
        删除指定名称的宏
        
        Args:
            macro_name: 宏名称
            
        Returns:
            删除的文件数量，如果出错返回 0
        """
        if not macro_name:
            logger.warning("Macro name is empty, cannot delete")
            return 0
        
        if not os.path.exists(SCRIPT_PATH):
            logger.warning(f"Script path does not exist: {SCRIPT_PATH}")
            return 0
        
        try:
            target_filepath = self._find_script_files_by_name(macro_name, is_macro=True)

            # 删除成功后，重新初始化脚本字典
            deleted_count = 0
            for file_path in target_filepath:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")
                    continue
            if deleted_count > 0:
                self.init_scripts_dict()
                logger.info(f"Deleted {deleted_count} file(s) for macro '{macro_name}'")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete macro '{macro_name}': {e}")
            return 0
    
    def open_macro_folder(self):
        """打开宏文件夹（实际上和路线文件夹是同一个）"""
        try:
            if os.path.exists(SCRIPT_PATH):
                os.startfile(SCRIPT_PATH)
                logger.info(f"Opened macro folder: {SCRIPT_PATH}")
            else:
                return False, f"宏文件夹不存在:{SCRIPT_PATH}"
        except Exception as e:
            logger.error(f"Failed to open macro folder: {e}")
            return False, f"无法打开宏文件夹:{str(e)}"
        return True, f"已打开宏文件夹:{SCRIPT_PATH}"

scripts_manager = ScriptsManager()
