import psutil
import win32gui, win32process, win32con
from whimbox.common.cvars import PROCESS_NAME

def get_hwnd_for_pid(pid):
    hwnds = []

    def callback(hwnd, hwnds):
        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
        # 检查是否属于目标进程，且窗口是可见并且不是子窗口
        if found_pid == pid and win32gui.IsWindowVisible(hwnd) and win32gui.GetParent(hwnd) == 0:
            hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(callback, hwnds)
    if hwnds:
        return hwnds[0]
    else:
        return 0

def _get_handle(process_name=None, pid=None):
    """获得游戏窗口句柄"""
    if pid is not None:
        hwnd = get_hwnd_for_pid(pid)
        return hwnd
    elif process_name is not None:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process_name:
                pid = proc.info['pid']
                hwnd = get_hwnd_for_pid(pid)
                return hwnd
        return 0

class ProcessHandler():
    def __init__(self, process_name=None, pid=None) -> None:
        self.process_name = process_name
        self.pid = pid
        if self.process_name is not None:
            self.handle = _get_handle(self.process_name)
        elif self.pid is not None:
            self.handle = _get_handle(self.pid)

    def get_handle(self):
        return self.handle

    def refresh_handle(self):
        self.handle = _get_handle(self.process_name, self.pid)
    
    def is_foreground(self):
        return win32gui.GetForegroundWindow() == self.handle
    
    def is_minimized(self):
        return win32gui.IsIconic(self.handle)

    def set_foreground(self):
        if self.is_alive():
            # 如果窗口被最小化，先恢复显示
            # if win32gui.IsIconic(self.handle):
            win32gui.ShowWindow(self.handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.handle)
    
    def is_alive(self):
        if not self.handle:
            return False
        # 检查窗口句柄是否仍然有效
        if not win32gui.IsWindow(self.handle):
            return False
        return True

    def check_shape(self):
        if self.is_alive():
            _, _, width, height = win32gui.GetClientRect(self.handle)
            if width <= 0:
                return False, 0, 0
            elif 1.55 < width/height < 1.80:
                # 支持16:9和16:10分辨率
                # 有些用户在特定显示器和缩放下会生成奇怪的1920x1081分辨率，增加宽容度
                return True, width, height
            else:
                return False, width, height
        return False, 0, 0
            

HANDLE_OBJ = ProcessHandler(PROCESS_NAME)

if __name__ == '__main__':
    pass
