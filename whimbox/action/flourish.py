from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.ui_utils import *
from whimbox.task.task_template import *
from whimbox.ability.ability import ability_manager
from whimbox.ability.cvar import ABILITY_NAME_FLOURISH

class FlourishTask(TaskTemplate):
    def __init__(self):
        super().__init__("FlourishTask")
    
    @register_step("开始芳间巡游")
    def step1(self):
        ability_manager.change_ability(ABILITY_NAME_FLOURISH)
        itt.right_click()
        time.sleep(4)
        itt.key_press(keybind.KEYBIND_ABILITY_DERIVATION_WORLD_1)
        time.sleep(5)
        itt.right_click()

if __name__ == "__main__":
    task = FlourishTask()
    task.task_run()