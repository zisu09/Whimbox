'''魔物试炼幻境'''
from whimbox.task.task_template import TaskTemplate, register_step
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.common.utils.ui_utils import *
from whimbox.common.cvars import DEBUG_MODE
from whimbox.config.config import global_config

class MonsterTask(TaskTemplate):
    def __init__(self, level_name=None):
        super().__init__("monster_task")
        if not level_name:
            self.level_name = global_config.get("Game", "monster_target")
        else:
            self.level_name = level_name
    

    @register_step("正在前往魔物试炼幻境")
    def step1(self):
        ui_control.goto_page(page_huanjing_monster)
    

    @register_step("选择试炼")
    def step2(self):
        self.log_to_gui(f"选择试炼：{self.level_name}")
        if not scroll_find_click(AreaBlessHuanjingLevelsSelect, self.level_name, str_match_mode=1):
            raise Exception(f"未找到{self.level_name}")
        
    
    @register_step("开始快速挑战")
    def step3(self):
        if not wait_until_appear_then_click(ButtonBlessHuanjingQuickPlay):
            raise Exception("未找到快速挑战按钮")
        time.sleep(0.5) #等待窗口弹出
        # 如果当前幻境就是默认消耗体力的幻境，就把次数调到最大
        default_energy_cost = global_config.get("Game", "energy_cost")
        if default_energy_cost == "魔物试炼幻境":
            self.log_to_gui("已允许消耗所有活跃能量！")
            if not DEBUG_MODE:
                wait_until_appear_then_click(ButtonBlessHuanjingNumMax)
                time.sleep(0.2)
            else:
                self.log_to_gui("debug下，不消耗所有能量，为了能多测几次")
        if not wait_until_appear_then_click(ButtonHuanjingConfirm):
            self.log_to_gui("未找到注入能量按钮", is_error=True)
            wait_until_appear_then_click(ButtonHuanjingCancel)
            return "step5"

    @register_step("等待挑战完成")
    def step4(self):
        if skip_get_award():
            self.update_task_result(message="魔物试炼幻境完成")
        else:
            raise Exception("领取奖励失败")

    @register_step("退出魔物试炼幻境")
    def step5(self):
        ui_control.goto_page(page_main)


if __name__ == "__main__":
    monster_task = MonsterTask()
    monster_task.task_run()
        

