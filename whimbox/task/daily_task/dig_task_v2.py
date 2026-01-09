"""
美鸭梨挖掘
"""

from whimbox.task.task_template import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.ui_utils import *

class DigTaskV2(TaskTemplate):
    def __init__(self):
        super().__init__("dig_task_v2")
    
    @register_step("正在前往美鸭梨挖掘")
    def step1(self):
        ui_control.goto_page(page_esc)
        if not scroll_find_click(AreaEscEntrances, "美鸭梨挖掘"):
            raise Exception("美鸭梨挖掘入口未找到")
        itt.wait_until_stable(threshold=0.95)


    @register_step("判断是否可收获")
    def step2(self):
        if itt.appear_then_click(ButtonDigGather):
            return "step3" # 可一键收获
        else:
            dig_num_str = itt.ocr_single_line(AreaDigingNumText, padding=50)
            try:
                diging_num = int(dig_num_str.split("/")[0])
            except:
                raise Exception(f"挖掘数量识别异常:{dig_num_str}")
            if diging_num > 0:
                self.log_to_gui(f"当前正在挖掘{dig_num_str}")
                self.update_task_result(status=STATE_TYPE_FAILED, message=f"正在挖掘，无法收获", data=False)
                return "step4" # 有东西正在挖掘，退出
            else:
                self.update_task_result(status=STATE_TYPE_FAILED, message=f"没有东西在挖掘，请手动设置挖掘目标", data=False)
                return "step4" # 没东西在挖掘，退出


    @register_step("一键收获并再次挖掘")
    def step3(self):
        if wait_until_appear_then_click(ButtonDigAgain):
            self.update_task_result(message=f"成功一键收获并再次挖掘", data=True)
        self.update_task_result(status=STATE_TYPE_FAILED, message="未弹出挖掘结果窗口", data=False)
        return "step4"

    @register_step("退出美鸭梨挖掘")
    def step4(self):
        back_to_page_main()

if __name__ == "__main__":
    dig_task = DigTaskV2()
    dig_task.task_run()