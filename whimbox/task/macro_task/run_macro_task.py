from whimbox.task.task_template import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.scripts_manager import *
from whimbox.common.logger import logger
import time
from whimbox.common.scripts_manager import *
from whimbox.common.handle_lib import HANDLE_OBJ
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *


class RunMacroTask(TaskTemplate):
    """运行宏记录的任务"""
    
    def __init__(self, session_id, macro_filename: str, delay=0, check_stop_func=None):
        super().__init__(session_id=session_id, name="run_macro_task")
        self.check_stop_func = check_stop_func
        self.delay = delay
        self.macro_record = scripts_manager.query_macro(macro_filename, return_one=True)
        if not self.macro_record:
            raise ValueError(f"宏\"{macro_filename}\"不存在，请先下载该宏")
        if self.macro_record and self.macro_record.info.version != "3.0":
            raise ValueError(f"宏版本不匹配，请更新宏")
        self.is_play_music = False
        if self.macro_record.info.type == "乐谱":
            self.is_play_music = True

        self.current_step_index = 0
        self.pressing_keys = set()
    
    def _execute_step(self, step: MacroStep):
        """执行单个宏步骤"""
        try:
            if step.type == "gap":
                # 间隔等待
                if step.duration and step.duration > 0:
                    time.sleep(step.duration)
                    
            elif step.type == "keyboard":
                # 键盘操作
                if step.action == "press":
                    itt.key_down(step.key)
                    self.pressing_keys.add(step.key)
                elif step.action == "release":
                    itt.key_up(step.key)
                    self.pressing_keys.discard(step.key)
                    
            elif step.type == "mouse":
                # 鼠标按键操作
                if step.position:
                    # 移动到目标位置并点击
                    if step.action == "press":
                        itt.move_to(step.position)
                        itt.key_down(step.key)
                        self.pressing_keys.add(step.key)
                    elif step.action == "release":
                        itt.move_to(step.position)
                        itt.key_up(step.key)
                        self.pressing_keys.discard(step.key)
            
            elif step.type == "wait_game_page":
                # 等待某个特定游戏页面
                if step.target_game_page not in ui_page_dict:
                    raise Exception(f"不支持检测「{step.target_game_page}」页面")
                else:
                    while not ui_control.verify_page(ui_page_dict[step.target_game_page]):
                        time.sleep(0.1)
            
            elif step.type == "goto_game_page":
                # 前往某个特定游戏页面
                if step.target_game_page not in ui_page_dict:
                    raise Exception(f"不支持前往「{step.target_game_page}」页面")
                else:
                    ui_control.goto_page(ui_page_dict[step.target_game_page])
                    
        except Exception as e:
            logger.error(f"执行步骤失败: {e}, step: {step}")

    @register_step(state_msg="执行宏操作")
    def execute_macro(self):
        if self.is_play_music:
            # 乐谱宏，检查当前是否在演奏界面
            if not page_play_music.is_current_page(itt):
                self.update_task_result(status=STATE_TYPE_FAILED, message="未进入演奏界面")
                return STEP_NAME_FINISH
        else:
            # 普通宏，检查分辨率
            aspect_ratio = self.macro_record.info.aspect_ratio
            _, width, height = HANDLE_OBJ.check_shape()
            if aspect_ratio == "16:9" and not (1.70<width/height<1.80):
                self.update_task_result(status=STATE_TYPE_FAILED, message=f"宏\"{self.macro_record.info.name}\"只支持16:9分辨率，请修改游戏设置")
                return STEP_NAME_FINISH
            elif aspect_ratio == "16:10" and not (1.55<width/height<1.65):
                self.update_task_result(status=STATE_TYPE_FAILED, message=f"宏\"{self.macro_record.info.name}\"只支持16:10分辨率，请修改游戏设置")
                return STEP_NAME_FINISH

        # 如果有延迟，先等待
        if self.delay > 0:
            time.sleep(self.delay)
        
        # 执行宏操作
        start_time = time.time()
        
        i = 0
        while i < len(self.macro_record.steps):
            if self.need_stop():
                break
            if self.check_stop_func and self.check_stop_func():
                break
            
            step = self.macro_record.steps[i]
            self.current_step_index = i
            
            # 处理循环步骤
            if step.type == "loop":
                if step.loop_count and step.loop_steps:
                    loop_start_index = i + 1
                    loop_end_index = min(i + 1 + step.loop_steps, len(self.macro_record.steps))
                    
                    self.log_to_gui(f"开始循环宏: 从步骤 {loop_start_index} 到 {loop_end_index-1}, 循环 {step.loop_count} 次")
                    
                    # 获取循环内的步骤
                    loop_steps = self.macro_record.steps[loop_start_index:loop_end_index]
                    if not loop_steps:
                        logger.warning(f"循环范围为空，跳过")
                        i += 1
                        continue
                    
                    # 执行循环
                    for loop_iteration in range(step.loop_count):
                        if self.need_stop() or (self.check_stop_func and self.check_stop_func()):
                            break
                        
                        self.log_to_gui(f"循环第 {loop_iteration + 1}/{step.loop_count} 次")
                        
                        # 执行循环内的每个步骤
                        for loop_step in loop_steps:
                            if self.need_stop() or (self.check_stop_func and self.check_stop_func()):
                                break
                            self._execute_step(loop_step)
                    
                    # 跳过已经循环执行的步骤
                    i = loop_end_index
                    continue
                else:
                    logger.warning(f"循环步骤缺少必要参数: loop_count={step.loop_count}, loop_steps={step.loop_steps}")
            else:
                # 普通步骤，直接执行
                self._execute_step(step)
            
            i += 1
        
        execution_time = time.time() - start_time
        self.log_to_gui(f"宏执行结束！耗时: {execution_time:.2f}秒")
    
    def handle_finally(self):
        """清理资源"""
        for key in self.pressing_keys:
            itt.key_up(key)
        # 不调用父类的 handle_finally，因为不需要返回主界面

if __name__ == "__main__":
    task = RunMacroTask(session_id="debug", macro_filename="进出幻境刷怪宏")
    task.task_run()

