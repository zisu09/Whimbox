from whimbox.task.task_template import *
from whimbox.interaction.interaction_core import itt
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.map.convert import convert_GameLoc_to_PngMapPx
from whimbox.map.map import nikki_map
from whimbox.map.detection.cvars import MAP_NAME_STARSEA
from whimbox.common.keybind import keybind
from whimbox.common.utils.ui_utils import *
from whimbox.task.navigation_task.auto_path_task import AutoPathTask

class XinghaiRunTask(TaskTemplate):
    def __init__(self):
        super().__init__("xinghai_run_task")
        self.target_loc = None

    @register_step("传送到星海无界枢纽")
    def step0(self):
        map_loc = convert_GameLoc_to_PngMapPx([-35070.57421875, 44421.59765625], MAP_NAME_STARSEA)
        nikki_map.bigmap_tp(map_loc, MAP_NAME_STARSEA)

    @register_step("摇铃")
    def step1(self):
        itt.key_down(keybind.KEYBIND_BELL)
        time.sleep(3)
        itt.key_up(keybind.KEYBIND_BELL)
        wait_until_appear(IconPageMainFeature, retry_time=10)

    @register_step("查看星光结晶位置")
    def step2(self):
        ui_control.goto_page(page_bigmap)
        box = find_game_img(GameImgStarCrystal, itt.capture(), threshold=0.70, scale=1)
        if box:
            itt.move_and_click(area_center(box))
            itt.wait_until_stable(threshold=0.9995)
        else:
            self.update_task_result(status=STATE_TYPE_FAILED, message="地图上未找到星光结晶")
            return "step_finish"

        boxes = find_game_img(GameImgStarCrystal, itt.capture(), threshold=0.70, scale=1, count=3)
        if boxes and len(boxes) > 0:
            centers = [area_center(box) for box in boxes]
            # 计算三个box的中心坐标（重心）
            triangle_center_x = sum(center[0] for center in centers) / len(centers)
            triangle_center_y = sum(center[1] for center in centers) / len(centers)
            triangle_center = (triangle_center_x, triangle_center_y)
            logger.debug(f"星光结晶中心坐标: {triangle_center}")
        else:
            self.update_task_result(status=STATE_TYPE_FAILED, message="地图上未找到星光结晶")
            return "step_finish"
        
        # 拖到屏幕中心
        itt.move_to(triangle_center)
        itt.left_down()
        # 瞎几把拖几下地图，防止游戏没反应过来
        for i in range(5):
            itt.move_to([10, 10], relative=True)
            if i % 2 == 0:
                itt.left_down()
        for i in range(5):
            itt.move_to([-10, -10], relative=True)
            if i % 2 == 0:
                itt.left_down()
        time.sleep(0.2)
        itt.move_to((1920/2, 1080/2), anchor=ANCHOR_CENTER)
        time.sleep(0.2)
        itt.move_to((1920/2, 1080/2), anchor=ANCHOR_CENTER)
        itt.left_up()

        self.target_loc = nikki_map.get_bigmap_posi()
        logger.debug(f"星光结晶地图坐标: {self.target_loc}")

    @register_step("开始跑图收集星光结晶")
    def step3(self):
        auto_path_dict = {
            "星海拾光_星光结晶收集_星梦群屿": (2878.8, 2164.0),
            "星海拾光_星光结晶收集_泡泡梦屿": (3120.0, 1908.3),
        }
        for path_name, loc in auto_path_dict.items():
            if loc[0]-50 <self.target_loc[0] < loc[0]+50 and loc[1]-50 <self.target_loc[1] < loc[1]+50:
                auto_path_task = AutoPathTask(path_name=path_name)
                task_result = auto_path_task.task_run()
                if task_result.status == STATE_TYPE_SUCCESS:
                    self.update_task_result(status=STATE_TYPE_SUCCESS, message="收集星光结晶成功")
                else:
                    self.update_task_result(status=STATE_TYPE_FAILED, message="收集星光结晶失败")
                return
        self.update_task_result(status=STATE_TYPE_FAILED, message="暂时没有这条收集路线，等俺更新~")

if __name__ == "__main__":
    task = XinghaiRunTask()
    print(task.task_run())
        
        