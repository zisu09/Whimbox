from whimbox.task.task_template import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.handle_lib import HANDLE_OBJ

class CloseGameTask(TaskTemplate):
    def __init__(self, session_id):
        super().__init__(session_id=session_id, name="close_game_task")
    
    @register_step("关闭游戏")
    def step1(self):
        HANDLE_OBJ.close_handle()

    def handle_finally(self):
        pass

if __name__ == "__main__":
    task = CloseGameTask(session_id="debug")
    print(task.task_run())
