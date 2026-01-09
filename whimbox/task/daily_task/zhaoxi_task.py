"""
检查并领取朝夕心愿
"""

from whimbox.task.task_template import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.interaction.interaction_core import itt
import time
from whimbox.common.utils.ui_utils import *
from whimbox.task.daily_task.cvar import *
from whimbox.common.logger import logger
from whimbox.task.navigation_task.auto_path_task import AutoPathTask
from whimbox.task.photo_task.daily_photo_task import DailyPhotoTask
from whimbox.task import daily_task


zxxy_task_info_list = [
    {
        "key_words": ["150点活跃能量"],
        "score": 200,
        "priority": 5,
        "task_name": DAILY_TASK_COST_ENERGY
    },
    {
        "key_words": ["素材激化幻境"],
        "score": 200,
        "priority": 5,
        "task_name": DAILY_TASK_JIHUA
    },
    {
        "key_words": ["幻境", "祝福闪光"],
        "score": 200,
        "priority": 5,
        "task_name": DAILY_TASK_GET_BLESS
    },
    {
        "key_words": ["魔物试炼幻境"],
        "score": 200,
        "priority": 5,
        "task_name": DAILY_TASK_MONSTER
    },
    {
        "key_words": ["植物"],
        "score": 200,
        "priority": 4,
        "task_name": DAILY_TASK_PICKUP
    },
    {
        "key_words": ["昆虫"],
        "score": 200,
        "priority": 3,
        "task_name": DAILY_TASK_CATCH_INSECT
    },
    {
        "key_words": ["小游戏"],
        "score": 200,
        "priority": 1,
        "task_name": DAILY_TASK_MINIGAME
    },
    {
        "key_words": ["照片"],
        "score": 100,
        "priority": 5,
        "task_name": DAILY_TASK_TAKE_PHOTO
    },
    {
        "key_words": ["挖掘"],
        "score": 100,
        "priority": 0,
        "task_name": DAILY_TASK_DIG
    },
    {
        "key_words": ["升级", "祝福闪光"],
        "score": 100,
        "priority": 0,
        "task_name": DAILY_TASK_UPGRADE_BLESSED
    },
    {
        "key_words": ["魔气怪"],
        "score": 100,
        "priority": 0,
        "task_name": DAILY_TASK_FIGHT
    },
    {
        "key_words": ["制作"],
        "score": 100,
        "priority": 0,
        "task_name": DAILY_TASK_MAKE_CLOTHES
    },
]


class ZhaoxiTask(TaskTemplate):
    def __init__(self):
        super().__init__("zhaoxi_task")
        self.current_score = 0

    @register_step("检查朝夕心愿完成情况")
    def step1(self):
        ui_control.goto_page(page_zxxy)
        try:
            itt.wait_until_stable(threshold=0.95)
            score_str = itt.ocr_single_line(AreaZxxyScore)
            score = int(score_str.strip())
            if score % 100 != 0:
                raise Exception(f"朝夕心愿分数识别异常:{score_str}")
        except:
            raise Exception(f"朝夕心愿分数识别异常:{score_str}")
        self.current_score = score
        if score == 500:
            return "step5"
        else:
            self.log_to_gui(f"朝夕心愿完成度：{score}/500")
            return


    @register_step("查看朝夕心愿具体任务")
    def step2(self):
        def check_task(click_pos):
            itt.move_and_click(click_pos, anchor=ANCHOR_CENTER)
            time.sleep(0.3)
            if not itt.get_img_existence(IconZxxyTaskFinished):
                task_text = itt.ocr_single_line(AreaZxxyTaskText)
                logger.info(f"任务文本：{task_text}")
                for task_info in zxxy_task_info_list:
                    is_match = True
                    for key_word in task_info["key_words"]:
                        if key_word not in task_text:
                            is_match = False
                            break
                    if is_match:
                        return task_info
                return None
            else:
                return None

        # 获得未完成任务列表
        self.unfinished_tasks = []
        for click_pos in DAILY_TASK_CENTERS:
            if self.need_stop():
                break
            unfinished_task = check_task(click_pos)
            if unfinished_task == None:
                continue
            else:
                self.log_to_gui(f"未完成任务：{unfinished_task['task_name']}")
                self.unfinished_tasks.append(unfinished_task)
        
        # 根据优先级和分数排序
        self.unfinished_tasks.sort(
            key=lambda x: (x['priority'], x['score']),
            reverse=True
        )

    @register_step("开始做朝夕心愿任务")
    def step3(self):
        task_dict = {
            DAILY_TASK_PICKUP: AutoPathTask(path_name="朝夕心愿_采集", excepted_num=5),
            DAILY_TASK_CATCH_INSECT: AutoPathTask(path_name="朝夕心愿_捕虫", excepted_num=3),
            DAILY_TASK_MINIGAME: AutoPathTask(path_name="朝夕心愿_小游戏"),
            DAILY_TASK_GET_BLESS: daily_task.BlessTask(),
            DAILY_TASK_JIHUA: daily_task.JihuaTask(),
            DAILY_TASK_MONSTER: daily_task.MonsterTask(),
            DAILY_TASK_TAKE_PHOTO: DailyPhotoTask(),
        }
        self.done_task_names = []
        for task in self.unfinished_tasks:
            if self.current_score >= 500 or self.need_stop():
                break
            task_name = task['task_name']
            if task_name == DAILY_TASK_COST_ENERGY:
                # 消耗体力留到最后再做，为了避免体力不够做，分数就不加了
                pass
            elif task_name in task_dict:
                task_obj = task_dict[task_name]
                result = task_obj.task_run()
                if result.status == STATE_TYPE_SUCCESS:
                    self.current_score += task['score']
                    self.done_task_names.append(task_name)
                else:
                    self.log_to_gui(f"任务\"{task_name}\"失败，继续其他任务", is_error=True)
            else:
                self.log_to_gui(f"暂不支持任务\"{task_name}\"，继续其他任务", is_error=True)
    
    @register_step("消耗剩余体力")
    def step4(self):
        energy_cost = global_config.get("Game", "energy_cost")
        if energy_cost == "不消耗剩余体力":
            self.log_to_gui("已设置不消耗剩余体力，跳过")
        elif energy_cost == "素材激化幻境":
            if DAILY_TASK_JIHUA not in self.done_task_names:
                task = daily_task.JihuaTask()
                task.task_run()
            else:
                self.log_to_gui("体力在做日常时以消耗，跳过")
        elif energy_cost == "祝福闪光幻境":
            if DAILY_TASK_GET_BLESS not in self.done_task_names:
                task = daily_task.BlessTask()
                task.task_run()
            else:
                self.log_to_gui("体力在做日常时以消耗，跳过")
        elif energy_cost == "魔物试炼幻境":
            if DAILY_TASK_MONSTER not in self.done_task_names:
                task = daily_task.MonsterTask()
                task.task_run()
            else:
                self.log_to_gui("体力在做日常时以消耗，跳过")
        else:
            self.log_to_gui("未配置默认消耗体力方式", is_error=True)

    @register_step("领取朝夕心愿奖励")
    def step5(self):
        ui_control.goto_page(page_zxxy)
        itt.delay(1, comment="等待页面稳定")
        if not itt.get_img_existence(ButtonZxxyRewarded):
            ButtonZxxyRewarded.click()
            if skip_get_award():
                self.update_task_result(message="成功领取朝夕心愿奖励")
            else:
                self.update_task_result(status=STATE_TYPE_FAILED, message="朝夕心愿未完成")
        else:
            self.update_task_result(message="朝夕心愿奖励已被领取过，无需再次领取")


    @register_step("退出朝夕心愿")
    def step6(self):
        ui_control.goto_page(page_main)
    

if __name__ == "__main__":
    zhaoxi_task = ZhaoxiTask()
    zhaoxi_task.task_run()
    print(zhaoxi_task.task_result)