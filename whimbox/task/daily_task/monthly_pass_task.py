'''领取大月卡奖励'''
from whimbox.task.task_template import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
import time
from whimbox.common.utils.ui_utils import *

class MonthlyPassTask(TaskTemplate):
    def __init__(self, session_id):
        super().__init__(session_id=session_id, name="monthly_pass_task")

    @register_step("打开奇迹之旅")
    def step1(self):
        ui_control.goto_page(page_monthly_pass)
    
    @register_step("领取奖励")
    def step2(self):
        if wait_until_appear_then_click(TextMonthlyPassTab2):
            if wait_until_appear_then_click(ButtonMonthlyPassAward):
                skip_get_award()
            time.sleep(0.5)
            if wait_until_appear_then_click(TextMonthlyPassTab1):
                if wait_until_appear_then_click(ButtonMonthlyPassAward):
                    if skip_get_award():
                        self.update_task_result(message="成功领取奇迹之旅奖励")
                        return
                    else:
                        self.update_task_result(status=STATE_TYPE_FAILED, message="领取奇迹之旅奖励失败")
                        return
        self.update_task_result(message="奇迹之旅无奖励可领取")
        
    @register_step("退出奇迹之旅")
    def step3(self):
        ui_control.goto_page(page_main)

if __name__ == "__main__":
    task = MonthlyPassTask(session_id="debug")
    result = task.task_run()
    print(result.to_dict())

