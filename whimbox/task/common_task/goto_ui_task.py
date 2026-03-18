from whimbox.task.task_template import *
from whimbox.ui.page_assets import ui_page_dict
from whimbox.ui.ui import ui_control

class GotoUITask(TaskTemplate):
    def __init__(self, session_id, page_name):
        super().__init__(session_id=session_id, name="goto_ui_task")
        self.page_name = page_name
    
    @register_step("前往指定界面")
    def step1(self):
        if self.page_name in ui_page_dict:
            ui_control.goto_page(ui_page_dict[self.page_name])
            self.update_task_result(status=STATE_TYPE_SUCCESS, message=f"前往「{self.page_name}」成功")
        else:
            self.update_task_result(status=STATE_TYPE_FAILED, message=f"不支持前往「{self.page_name}」")

    def handle_finally(self):
        pass

if __name__ == "__main__":
    task = GotoUITask(session_id="debug")
    print(task.task_run())

