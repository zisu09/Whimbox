import psutil
import ctypes
import win32api
import win32gui, win32process, win32con
from whimbox.common.cvars import PROCESS_NAME
from whimbox.common.logger import logger

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
        def _activate_window(hwnd):
            # 先把窗口恢复到可见状态
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            fg_hwnd = win32gui.GetForegroundWindow()
            current_tid = win32api.GetCurrentThreadId()
            target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            fg_tid = 0
            if fg_hwnd:
                fg_tid, _ = win32process.GetWindowThreadProcessId(fg_hwnd)

            attached_fg = False
            attached_target = False

            def _safe_attach(src_tid, dst_tid, attach, label):
                if not src_tid or not dst_tid or src_tid == dst_tid:
                    return False
                try:
                    win32process.AttachThreadInput(src_tid, dst_tid, attach)
                    return True
                except Exception as exc:
                    logger.warning(
                        f"AttachThreadInput {label} failed: {exc}; "
                        f"src_tid={src_tid}, dst_tid={dst_tid}, fg_hwnd={fg_hwnd}, hwnd={hwnd}"
                    )
                    return False

            try:
                attached_fg = _safe_attach(current_tid, fg_tid, True, "foreground")
                attached_target = _safe_attach(current_tid, target_tid, True, "target")

                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
                win32gui.SetActiveWindow(hwnd)
                win32gui.SetFocus(hwnd)
            finally:
                if attached_target:
                    _safe_attach(current_tid, target_tid, False, "target-detach")
                if attached_fg:
                    _safe_attach(current_tid, fg_tid, False, "foreground-detach")

        try:
            if not self.is_alive():
                raise Exception("游戏窗口不存在")

            _activate_window(self.handle)
            if self.is_foreground():
                return

            # 某些系统会拦截首次前置，做一次顶置切换重试
            win32gui.SetWindowPos(
                self.handle,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
            )
            win32gui.SetWindowPos(
                self.handle,
                win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
            )
            _activate_window(self.handle)
            if self.is_foreground():
                return

            # Alt 键兜底（Windows 前台策略允许用户输入后切前台）
            user32 = ctypes.windll.user32
            user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
            user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            _activate_window(self.handle)
            if self.is_foreground():
                return
            raise Exception("无法将游戏窗口前置，被系统策略阻止")
        except Exception as e:
            logger.error(e)
            raise Exception("游戏窗口前置失败")
    
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
