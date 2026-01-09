from whimbox.common.utils.ui_utils import *
from whimbox.task.task_template import *
from whimbox.interaction.interaction_core import itt
from whimbox.ui.ui_assets import *
from whimbox.common.keybind import keybind

class PlaceItemTask(TaskTemplate):
    def __init__(self):
        super().__init__("place_item_task")

    @register_step("选择摆饰")
    def step1(self):
        itt.key_down(keybind.KEYBIND_ITEM)
        time.sleep(3)
        itt.key_up(keybind.KEYBIND_ITEM)
        if not wait_until_appear_then_click(ButtonItemSetting):
            raise Exception("未找到物品设置按钮")
        if not wait_until_appear_then_click(ButtonItemFinishSetting):
            raise Exception("未找到完成设置按钮")
        if not wait_until_appear_then_click(ButtonItemPlaceableItem):
            raise Exception("未找到摆饰按钮")
        itt.delay(0.5, comment="等待摆饰界面加载完成")
        AreaItemFirstItem.click()

        if wait_until_appear_then_click(ButtonItemLanternConfirm, retry_time=2):
            # 选中了河灯摆饰
            time.sleep(0.5)
            scroll_find_click(AreaDialog, "确认", str_match_mode=0, need_scroll=False)
            itt.delay(0.5, comment="等待退出摆饰选择界面")
            return

        if itt.get_img_existence(ButtonItemPlaceableItem):
            # 刚好这个摆饰之前放出去了，现在收回来了，需要再放一次
            AreaItemFirstItem.click()
            itt.delay(0.5, comment="等待退出摆饰选择界面")
            if itt.get_img_existence(ButtonItemPlaceableItem):
                raise Exception("选择摆饰失败")

    @register_step("放置摆饰")
    def step2(self):
        # 等待进入摆放界面，第一次掏出摆饰，可能会卡住
        while not self.need_stop():
            time.sleep(1)
            if not itt.get_img_existence(IconPageMainFeature):
                break

        itt.move_to((-200, 0), relative=True) # 先把摆饰挪远一点
        retry_time = 20
        while not self.need_stop() and retry_time > 0:
            itt.left_click()
            time.sleep(1)
            if itt.get_img_existence(IconItemCantPlace):
                itt.move_to((-200, 0), relative=True)
            else:
                self.update_task_result(status=STATE_TYPE_SUCCESS, message="摆饰放置成功")
                break
            retry_time -= 1
        if retry_time == 0:
            self.update_task_result(status=STATE_TYPE_FAILED, message="摆饰放置失败")
            itt.right_click()


if __name__ == "__main__":
    task = PlaceItemTask()
    result = task.task_run()
    print(result)