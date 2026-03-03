from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.ui_utils import *
from whimbox.task.task_template import *
from whimbox.ability.ability import ability_manager
from whimbox.ability.cvar import ABILITY_NAME_SHAPESHIFTING

class MagnetTask(TaskTemplate):
    def __init__(self, session_id):
        super().__init__(session_id=session_id, name="MagnetTask")
    
    @register_step("开启化万相小技能")
    def step1(self):
        if not ability_manager.change_ability(ABILITY_NAME_SHAPESHIFTING):
            self.update_task_result(status=STATE_TYPE_FAILED, message="切换化万相能力失败")
            return STEP_NAME_FINISH
        
        itt.delay(1, comment="稍等片刻")
        _, px_count = ability_manager.check_subability_active()
        itt.key_press(keybind.KEYBIND_ABILITY_DERIVATION_WORLD_1)
        itt.delay(0.5, comment="等待化万相小技能开启")
        _, new_px_count = ability_manager.check_subability_active()
        logger.info(f"化万相小技能开启前px_count: {px_count}, 开启后px_count: {new_px_count}")
        if new_px_count - px_count > 100:
            self.update_task_result(status=STATE_TYPE_SUCCESS, message="化万相小技能开启成功")
            return
        else:
            # 可能之前是开的，被我关了
            itt.key_press(keybind.KEYBIND_ABILITY_DERIVATION_WORLD_1)
            itt.delay(0.5, comment="等待化万相小技能开启")
            return
        
if __name__ == "__main__":
    task = MagnetTask(session_id="debug")
    print(task.task_run())

        