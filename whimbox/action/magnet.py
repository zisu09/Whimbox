from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.ui_utils import *
from whimbox.task.task_template import *
from whimbox.ability.ability import ability_manager
from whimbox.ability.cvar import ABILITY_NAME_SHAPESHIFTING

class MagnetTask(TaskTemplate):
    def __init__(self, session_id):
        super().__init__(session_id=session_id, name="MagnetTask")
    
    @register_step("开启扇子套小技能")
    def step1(self):
        if ability_manager.is_shapeshifting:
            self.update_task_result(status=STATE_TYPE_SUCCESS, message="之前已开启过扇子套小技能")
            return

        if not ability_manager.change_ability(ABILITY_NAME_SHAPESHIFTING):
            self.update_task_result(status=STATE_TYPE_FAILED, message="切换扇子套能力失败")
            return STEP_NAME_FINISH
        
        itt.delay(1, comment="稍等片刻")
        _, px_count = ability_manager.check_subability_active()
        itt.key_press(keybind.KEYBIND_ABILITY_DERIVATION_WORLD_1)
        itt.delay(2, comment="等待扇子套小技能开启")
        _, new_px_count = ability_manager.check_subability_active()
        logger.info(f"扇子套小技能开启前px_count: {px_count}, 开启后px_count: {new_px_count}")
        if new_px_count > px_count:
            pass
        else:
            # 可能之前是开的，被我关了
            itt.key_press(keybind.KEYBIND_ABILITY_DERIVATION_WORLD_1)
            itt.delay(0.5, comment="等待扇子套小技能开启")
        self.update_task_result(status=STATE_TYPE_SUCCESS, message="扇子套小技能开启成功")
        ability_manager.is_shapeshifting = True
        
if __name__ == "__main__":
    ability_manager.init_need_ability([ABILITY_NAME_SHAPESHIFTING])
    task = MagnetTask(session_id="debug")
    print(task.task_run())

        