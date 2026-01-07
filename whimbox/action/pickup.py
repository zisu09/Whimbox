from whimbox.task.task_template import TaskTemplate, register_step
from whimbox.interaction.interaction_core import itt
from whimbox.ui.ui_assets import *
from whimbox.common.cvars import DEBUG_MODE
from whimbox.common.utils.ui_utils import skip_to_page_main
from whimbox.common.keybind import keybind
from whimbox.common.utils.ui_utils import wait_until_appear
import time, re

class PickupTask(TaskTemplate):
    def __init__(self):
        super().__init__("pickup_task")
        self.material_count_dict = {}

    @register_step("开始采集")
    def step1(self):
        while not self.need_stop():
            if wait_until_appear(IconPickupFeature, area=AreaPickup, retry_time=2):
                itt.key_press(keybind.KEYBIND_INTERACTION)
                time.sleep(0.5) # 等待采集结果文字出现
                texts = itt.ocr_multiple_lines(AreaMaterialGetText)
                for text in texts:
                    if "精粹" in text or "心得" in text or "种子" in text:
                        continue
                    else:
                        pattern = r"^(.+?)[×xX]([0-9]+(?:\.[0-9]+)?)$"
                        match = re.match(pattern, text)
                        if match:
                            pickup_item = match.group(1)
                            if pickup_item in self.material_count_dict:
                                self.material_count_dict[pickup_item] += 1
                            else:
                                self.material_count_dict[pickup_item] = 1
                            break
            else:
                break
        
        if len(self.material_count_dict) == 0:
            self.update_task_result(message="未采集到物品")
            self.log_to_gui("未采集到物品")
            return
        count_str_list = []
        for key, value in self.material_count_dict.items():
            count_str_list.append(f"{key}x{value}")
        res = ",".join(count_str_list)
        res = f"获得{res}"
        self.update_task_result(
            message=res,
            data=self.material_count_dict
        )
        self.log_to_gui(res)

if __name__ == "__main__":
    while True:
        pickup_task = PickupTask()
        pickup_task.task_run()