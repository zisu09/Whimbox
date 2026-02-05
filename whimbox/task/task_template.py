from whimbox.common.logger import logger
from whimbox.common.utils.ui_utils import back_to_page_main
from whimbox.common.cvars import (
    current_stop_flag, 
    get_current_stop_flag,
    set_foreground_task_running
)

from pynput import keyboard
import time
import traceback
import threading

STATE_TYPE_SUCCESS = "success"  # 成功
STATE_TYPE_ERROR = "error"      # 错误，会引发一次重试
STATE_TYPE_STOP = "stop"        # 手动停止，不会引发重试
STATE_TYPE_FAILED = "failed"    # 失败，不会引发重试

STEP_NAME_FINISH = "step_finish"

class state:
    def __init__(self, type="", msg=""):
        self.type = type
        self.msg = msg

class TaskStep:
    def __init__(self, func, name=None, state_type="", state_msg=""):
        self.func = func
        self.state = state(state_type, state_msg)
        self.name = name or func.__name__

    def run(self):
        """运行步骤函数，返回下一步的名称（可选）"""
        return self.func()

def register_step(state_msg=""):
    """类方法装饰器，用于标记需要注册的步骤"""
    def wrapper(func):
        func._register_step = True
        func._state_msg = state_msg
        return func
    return wrapper

class TaskResult:
    def __init__(self, status=STATE_TYPE_SUCCESS, message="", data=None):
        self.status = status
        self.message = message
        self.data = data
    
    def to_dict(self):
        return self.__dict__

    def __str__(self) -> str:
        return f"{{'status': {self.status}, 'message': {self.message}}}"

class TaskTemplate:
    def __init__(self, name=""):
        self.name = name
        
        # 尝试从 context 获取父任务的 stop_flag
        stop_flag = current_stop_flag.get()
        
        if stop_flag is None:
            # 这是顶层任务，创建新的 stop_flag
            stop_flag = threading.Event()
            current_stop_flag.set(stop_flag)
            self.is_top_level_task = True
            logger.info(f"创建顶层任务: {self.name}")
        else:
            # 这是子任务，复用父任务的 stop_flag
            self.is_top_level_task = False
            logger.info(f"创建子任务: {self.name}")
        
        # 保存为实例属性，供 pynput 回调和任务内部使用
        self.stop_flag = stop_flag
        
        self.step_sleep = 0.2   # 步骤执行后等待时间
        self.steps_dict = {}    # {step_name: TaskStep} 步骤字典
        self.step_order = []    # [step_name, ...] 默认执行顺序
        self.current_step: TaskStep = None
        self.error_step = TaskStep(lambda step, task: None, STATE_TYPE_ERROR, "")
        self.task_result = TaskResult()
        self.__auto_register_steps()

        # 只有顶层任务才创建 pynput 监听器
        if self.is_top_level_task:
            self.key_callbacks = {}  # 存储按键回调
            self.listener = keyboard.Listener(on_press=self._on_key_press)
            self.listener.daemon = True  # 设为守护线程
            self.listener.start()
            # 添加默认停止热键
            self.add_hotkey("/", self.task_stop)
        else:
            self.key_callbacks = None
            self.listener = None

        
    def _on_key_press(self, key):
        """处理按键事件（仅在顶层任务中使用）"""
        try:
            if self.key_callbacks is None:
                return
            # 检查是否是字符键
            if hasattr(key, 'char') and key.char in self.key_callbacks:
                self.key_callbacks[key.char]()
            # 检查是否是特殊键
            elif key in self.key_callbacks:
                self.key_callbacks[key]()
        except Exception as e:
            logger.error(f"热键处理错误: {e}")

    def add_hotkey(self, key_str, callback):
        """添加热键监听（仅在顶层任务中有效）"""
        if self.key_callbacks is None:
            return
        # 将字符串键转换为pynput键对象
        if len(key_str) == 1:  # 单个字符
            self.key_callbacks[key_str] = callback
        else:
            try:
                # 尝试将键名转换为pynput.keyboard.Key对象
                key_obj = getattr(keyboard.Key, key_str)
                self.key_callbacks[key_obj] = callback
            except AttributeError:
                logger.warning(f"无法识别的键: {key_str}")


    def __auto_register_steps(self):
        """自动注册带有_register_step标记的方法"""
        # 获取类的所有方法，包括继承的
        for method_name in dir(self):
            # 跳过私有方法和特殊方法
            if method_name.startswith('__'):
                continue
            
            method = getattr(self, method_name)
            # 检查是否是可调用的方法且有注册标记
            if callable(method) and hasattr(method, "_register_step"):
                task_step = TaskStep(method, method_name, STATE_TYPE_SUCCESS, method._state_msg)
                self.steps_dict[method_name] = task_step
                self.step_order.append(method_name)


    def on_error(self, state_msg=""):
        """定义 error_step"""
        def wrapper(func):
            self.error_step = TaskStep(func, "error_step", STATE_TYPE_ERROR, state_msg)
            return func
        return wrapper

    def task_run(self):
        try:
            # 如果是顶层任务，设置前台任务运行标志
            if self.is_top_level_task:
                set_foreground_task_running(True)
            
            res = self._task_run()
            if res.status in [STATE_TYPE_SUCCESS, STATE_TYPE_STOP, STATE_TYPE_FAILED]:
                return res
            else:
                # 非手动停止导致的失败，就再试一次
                if not self.need_stop():
                    self.log_to_gui(f"自动返回主界面，重试一次")
                    back_to_page_main()
                    self.task_result = TaskResult() # 重置一下任务结果
                    res = self._task_run()
                    return res
                else:
                    return res
        finally:
            # 如果是顶层任务，清除前台任务运行标志
            if self.is_top_level_task:
                if self.listener:
                    self.key_callbacks.clear()
                    if self.listener.is_alive():
                        self.listener.stop()
                        self.listener.join()
                set_foreground_task_running(False)
                current_stop_flag.set(None)


    def _task_run(self):
        """核心执行逻辑"""
        current_step_name = self.step_order[0] if self.step_order else None
        
        try:
            while current_step_name != STEP_NAME_FINISH and not self.need_stop():
                # 获取当前步骤
                step = self.steps_dict.get(current_step_name)
                if not step:
                    raise Exception(f"步骤 '{current_step_name}' 不存在")
                
                self.current_step = step
                
                # 显示步骤信息
                if step.state.msg:
                    self.log_to_gui(step.state.msg)
                
                # 运行步骤
                next_step_name = step.run()
                
                # 确定下一步
                if next_step_name:
                    # 步骤函数指定了下一步
                    current_step_name = next_step_name
                else:
                    # 使用默认顺序的下一步
                    current_index = self.step_order.index(current_step_name)
                    if current_index + 1 < len(self.step_order):
                        current_step_name = self.step_order[current_index + 1]
                    else:
                        # 已到达最后一步
                        current_step_name = STEP_NAME_FINISH
                
                time.sleep(self.step_sleep)

        except Exception as e:
            self.handle_exception(e)
            self.error_step.state.msg = str(e)
            self.current_step = self.error_step
            self.update_task_result(status=STATE_TYPE_ERROR, message=self.error_step.state.msg)
            logger.error(traceback.format_exc())
        
        finally:
            self.handle_finally()
            # 显示任务结果
            if self.task_result.message:
                if self.task_result.status == STATE_TYPE_SUCCESS:
                    self.log_to_gui(self.task_result.message)
                else:
                    self.log_to_gui(self.task_result.message, is_error=True)
            return self.task_result


    def handle_exception(self, e):
        '''处理异常，如果子类有异常要处理，就实现这个方法'''
        pass

    def handle_finally(self):
        '''
        如果子类有需要在finally时进行的操作，就实现这个方法
        比如需要在结束时释放资源等等
        '''
        back_to_page_main()


    def task_stop(self, message=None, data=None):
        # 慎用此方法，会停止该任务链上的所有父任务子任务
        '''如果子类有自己额外的停止代码，就实现这个方法，并调用父类的这个方法'''
        if not self.stop_flag.is_set():
            self.stop_flag.set()
        self.update_task_result(status=STATE_TYPE_STOP, message=message or "停止任务", data=data)
        logger.info(f"停止任务: {self.name}")

    def need_stop(self):
        if self.stop_flag.is_set():
            if self.task_result.status != STATE_TYPE_STOP:
                self.update_task_result(status=STATE_TYPE_STOP)
            return True
        else:
            return False

    def get_state_msg(self):
        """获得当前任务的状态信息，供agent显示"""
        return self.current_step.state.msg if self.current_step else ""


    def log_to_gui(self, msg, is_error=False, type="update_ai_message"):
        if not is_error:
            msg = f"✅ {msg}\n"
        else:
            msg = f"❌ {msg}\n"
        from whimbox.ingame_ui.ingame_ui import win_ingame_ui
        if win_ingame_ui:
            win_ingame_ui.update_message(msg, type)
        logger.info(msg)


    def update_task_result(self, status=STATE_TYPE_SUCCESS, message="", data=None, force_update=False):
        # 如果先前是停止状态，则不更新
        if (not force_update) and self.task_result.status == STATE_TYPE_STOP:
            return
        else:
            self.task_result = TaskResult(status, message, data)