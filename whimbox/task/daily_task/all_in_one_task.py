'''朝夕心愿一条龙'''

from whimbox.task.task_template import *
from whimbox.task import daily_task
from whimbox.task.mira_crown_task.mira_crown_task import MiraCrownTask
from whimbox.task.daily_task.cvar import *
from whimbox.task.common_task.start_game_task import StartGameTask
from whimbox.map.detection.cvars import MAP_NAME_MIRALAND, MAP_NAME_UNSUPPORTED
from whimbox.map.convert import convert_GameLoc_to_PngMapPx
from whimbox.common.handle_lib import HANDLE_OBJ
from whimbox.task.daily_task.xinghai_run_task import XinghaiRunTask

class AllInOneTask(TaskTemplate):
    def __init__(self):
        super().__init__("all_in_one_task")
        self.zhaoxi_todo_list = []
        self.task_result_list = {
            'dig_task': False,
            'weekly_realm_task': False,
            'zhaoxi_task': False,
            'xinghai_run_task': False,
            'xinghai_task': False,
            'mira_crown_task': False,
            'monthly_pass_task': False,
        }

    @register_step("自动启动游戏")
    def step0(self):
        start_game_task = StartGameTask()
        task_result = start_game_task.task_run()
        if task_result.status == STATE_TYPE_SUCCESS:
            _, width, height = HANDLE_OBJ.check_shape()
            if width > 2560 or width < 1920:
                msg = f"当前游戏分辨率：{width}x{height}。推荐分辨率为：1920x1080或1920x1200或2560x1440或2560x1600。如遇到bug，请修改游戏分辨率后重试"
                self.log_to_gui(msg)
            return "step1"
        else:
            return STEP_NAME_FINISH


    @register_step("美鸭梨挖掘")
    def step1(self):
        dig_task = daily_task.DigTaskV2()
        task_result = dig_task.task_run()
        self.task_result_list['dig_task'] = task_result.status == STATE_TYPE_SUCCESS
        self.log_to_gui("检查是否在家园")
        from whimbox.map.map import nikki_map
        nikki_map.reinit_smallmap()
        # 如果在不支持的地图（比如家园），就传送到花愿镇
        if nikki_map.map_name == MAP_NAME_UNSUPPORTED:
            loc = convert_GameLoc_to_PngMapPx([-13172.34765625, -54273.6171875], MAP_NAME_MIRALAND)
            nikki_map.bigmap_tp(loc, MAP_NAME_MIRALAND)

    @register_step("检查周本进度")
    def step2(self):
        weekly_realm_task = daily_task.WeeklyRealmTask()
        task_result = weekly_realm_task.task_run()
        self.task_result_list['weekly_realm_task'] = task_result.status == STATE_TYPE_SUCCESS

    @register_step("开始完成朝夕心愿")
    def step3(self):
        zhaoxi_task = daily_task.ZhaoxiTask()
        task_result = zhaoxi_task.task_run()
        self.task_result_list['zhaoxi_task'] = task_result.status == STATE_TYPE_SUCCESS
    
    @register_step("收集星光结晶")
    def step4(self):
        xinghai_run_task = XinghaiRunTask()
        task_result = xinghai_run_task.task_run()
        self.task_result_list['xinghai_run_task'] = task_result.status == STATE_TYPE_SUCCESS

    @register_step("开始完成星海拾光")
    def step5(self):
        xinghai_task = daily_task.XinghaiTask()
        task_result = xinghai_task.task_run()
        self.task_result_list['xinghai_task'] = task_result.status == STATE_TYPE_SUCCESS

    @register_step("开始完成奇迹之冠巅峰赛")
    def step6(self):
        mira_crown_task = MiraCrownTask()
        task_result = mira_crown_task.task_run()
        self.task_result_list['mira_crown_task'] = task_result.status == STATE_TYPE_SUCCESS

    @register_step("领取奇迹之旅奖励")
    def step7(self):
        monthly_pass_task = daily_task.MonthlyPassTask()
        task_result = monthly_pass_task.task_run()
        self.task_result_list['monthly_pass_task'] = task_result.status == STATE_TYPE_SUCCESS

    @register_step("一条龙结束")
    def step8(self):
        msg = "任务结果如下：\n"

        if self.task_result_list['dig_task']:
            msg += "✅美鸭梨挖掘成功\n"
        else:
            msg += "❌美鸭梨挖掘还无法收获\n"

        if self.task_result_list['weekly_realm_task']:
            msg += "✅每周幻境已完成\n"
        else:
            msg += "❌每周幻境未完成\n"

        if self.task_result_list['zhaoxi_task']:
            msg += "✅朝夕心愿已完成\n"
        else:
            msg += "❌朝夕心愿未完成\n"

        if self.task_result_list['xinghai_run_task']:
            msg += "✅星光结晶收集已完成\n"
        else:
            msg += "❌星光结晶收集未完成\n"

        if self.task_result_list['xinghai_task']:
            msg += "✅星海拾光已完成\n"
        else:
            msg += "❌星海拾光未完成\n"

        if self.task_result_list['mira_crown_task']:
            msg += "✅奇迹之冠巅峰赛已完成\n"
        else:
            msg += "❌奇迹之冠巅峰赛未完成\n"

        if self.task_result_list['monthly_pass_task']:
            msg += "✅奇迹之旅已领取"
        else:
            msg += "❌奇迹之旅未领取"
            
        self.update_task_result(message=msg, data=self.task_result_list)


if __name__ == "__main__":
    task = AllInOneTask()
    # result = task.task_run()
    # print(result.to_dict())
    task.step3()
        