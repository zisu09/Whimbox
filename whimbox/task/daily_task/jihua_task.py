"""
激化素材幻境
"""

from whimbox.task.task_template import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.interaction.interaction_core import itt
import time
from whimbox.ui.material_icon_assets import material_icon_dict
from whimbox.common.utils.ui_utils import *
from whimbox.common.cvars import DEBUG_MODE
from whimbox.common.keybind import keybind

target_material_list = ["噗灵", "丝线", "闪亮泡泡"]

class JihuaTask(TaskTemplate):
    def __init__(self, target_material=None, cost_material=None):
        super().__init__("jihua_task")
        if target_material:
            self.target_material = target_material
        else:
            self.target_material = global_config.get("Game", "jihua_target")
        if cost_material:
            self.cost_materials = [cost_material]
        else:
            self.cost_materials = [
                global_config.get("Game", "jihua_cost"), 
                global_config.get("Game", "jihua_cost_2"), 
                global_config.get("Game", "jihua_cost_3")]

    @register_step("正在前往素材激化幻境")
    def step1(self):
        if self.target_material == '不做素材激化幻境':
            self.update_task_result(status=STATE_TYPE_FAILED, message="已设置不做素材激化幻境，跳过")
            return STEP_NAME_FINISH
        ui_control.goto_page(page_huanjing_jihua)


    @register_step("继续前往素材激化幻境")
    def step2(self):
        if not wait_until_appear_then_click(ButtonJihuaInnerGo):
            raise Exception("未找到素材激化幻境入口")


    @register_step("正在前往激化台")
    def step3(self):
        itt.wait_until_stable(threshold=0.95, timeout=2)
        ui_control.ui_additional()
        if not wait_until_appear(IconPageMainFeature, retry_time=10):
            raise Exception("未进入素材激化幻境")
        
        retry_time = 3
        while retry_time > 0:
            itt.key_down(keybind.KEYBIND_FORWARD)
            time.sleep(0.8)
            itt.key_up(keybind.KEYBIND_FORWARD)
            time.sleep(0.2) # 等待弹出按钮
            if itt.get_text_existence(TextJihuatai):
                itt.key_press(keybind.KEYBIND_INTERACTION)
                return
            retry_time -= 1
        else:
            raise Exception("未找到素材激化台")


    @register_step("选择兑换产物")
    def step4(self):
        if self.target_material not in target_material_list:
            raise Exception(f"不支持兑换激化产物{self.target_material}")
        itt.wait_until_stable()
        if not scroll_find_click(AreaJihuaTargetSelect, self.target_material):
            raise Exception(f"未找到激化产物{self.target_material}")
        itt.wait_until_stable(threshold=0.99)


    @register_step("选择激化素材")
    def step5(self):
        for cost_material in self.cost_materials:
            if cost_material not in material_icon_dict:
                self.log_to_gui(f"不支持使用{cost_material}作为消耗材料，尝试使用备选素材", is_error=True)
                continue
            material_info = material_icon_dict[cost_material]
            if not material_info["jihua"]:
                self.log_to_gui(f"{cost_material}不能用于激化，尝试使用备选素材", is_error=True)
                continue
            if not scroll_find_click(AreaJihuaCostSelect, material_info["icon"], threshold=0.73, scale=0.5):
                self.log_to_gui(f"未找到消耗材料{cost_material}，尝试使用备选素材", is_error=True)
                continue
            return
        self.update_task_result(status=STATE_TYPE_FAILED, message="未找到激化消耗材料")
        return "step9"


    @register_step("选择激化素材数量")
    def step6(self):
        # 如果当前幻境就是默认消耗体力的幻境，就把次数调到最大
        default_energy_cost = global_config.get("Game", "energy_cost")
        if default_energy_cost == "素材激化幻境":
            self.log_to_gui("已允许消耗所有活跃能量！")
            if not DEBUG_MODE:
                wait_until_appear_then_click(ButtonJihuaNumMax)
                time.sleep(0.2)
            else:
                self.log_to_gui("debug下，不消耗所有能量，为了能多测几次")
        if wait_until_appear_then_click(ButtonJihuaNumConfirm):
            return
        raise Exception("未弹出素材数量选择框")


    @register_step("确认开始激化")
    def step7(self):
        if not wait_until_appear_then_click(ButtonJihuaFinallyConfirm):
            self.log_to_gui("体力不够了，无法激化", is_error=True)
            return "step9"
        

    @register_step("等待激化完成")
    def step8(self):
        if wait_until_appear(IconSkip, retry_time=5):
            itt.delay(0.5, comment="以防万一，这里也加个延迟")
            itt.key_press(keybind.KEYBIND_INTERACTION)
        if skip_get_award():
            self.update_task_result(message="激化完成")
            return
        self.update_task_result(status=STATE_TYPE_FAILED, message="领取激化奖励失败")
        return

    @register_step("退出激化幻境")
    def step9(self):
        back_to_page_main()



if __name__ == "__main__":
    jihua_task = JihuaTask()
    result = jihua_task.task_run()
    print(result)