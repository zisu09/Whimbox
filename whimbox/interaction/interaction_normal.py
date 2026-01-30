import time
import ctypes
import win32api, win32con, win32gui

from whimbox.interaction.interaction_template import InteractionTemplate
from whimbox.interaction.vkcode import VK_CODE
from whimbox.common.cvars import *

class InteractionNormal(InteractionTemplate):

    def __init__(self, hwnd_handler):
        self.hwnd_handler = hwnd_handler
        self.WM_MOUSEMOVE = 0x0200
        self.WM_LBUTTONDOWN = 0x0201
        self.WM_LBUTTONUP = 0x202
        self.WM_MOUSEWHEEL = 0x020A
        self.WM_RBUTTONDOWN = 0x0204
        self.WM_RBUTTONDBLCLK = 0x0206
        self.WM_RBUTTONUP = 0x0205
        self.WM_KEYDOWN = 0x100
        self.WM_KEYUP = 0x101
        self.GetDC = ctypes.windll.user32.GetDC
        self.CreateCompatibleDC = ctypes.windll.gdi32.CreateCompatibleDC
        self.GetClientRect = ctypes.windll.user32.GetClientRect
        self.CreateCompatibleBitmap = ctypes.windll.gdi32.CreateCompatibleBitmap
        self.SelectObject = ctypes.windll.gdi32.SelectObject
        self.BitBlt = ctypes.windll.gdi32.BitBlt
        self.SRCCOPY = 0x00CC0020
        self.GetBitmapBits = ctypes.windll.gdi32.GetBitmapBits
        self.DeleteObject = ctypes.windll.gdi32.DeleteObject
        self.ReleaseDC = ctypes.windll.user32.ReleaseDC
        self.VK_CODE = VK_CODE
        self.PostMessageW = ctypes.windll.user32.PostMessageW
        self.MapVirtualKeyW = ctypes.windll.user32.MapVirtualKeyW
        self.VkKeyScanA = ctypes.windll.user32.VkKeyScanA
        self.WHEEL_DELTA = 120
        
    def left_click(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.1)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def left_down(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    
    def left_up(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    
    def left_double_click(self):
        self.left_click()
        time.sleep(0.05)
        self.left_click()
    
    def right_down(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)

    def right_up(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def right_click(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.1)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def middle_down(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
    
    def middle_up(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)

    def middle_click(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        time.sleep(0.1)
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
    
    def middle_scroll(self, distance):
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, distance*self.WHEEL_DELTA, 0)

    def key_down(self, key):
        vk_code = self.get_virtual_keycode(key)
        if key == 'shift':
            sc =  win32api.MapVirtualKey(win32con.VK_SHIFT, 0)
        else:
            sc = 0
        win32api.keybd_event(vk_code, sc, 0, 0)
    
    def key_up(self, key):
        vk_code = self.get_virtual_keycode(key)
        if key == 'shift':
            sc =  win32api.MapVirtualKey(win32con.VK_SHIFT, 0)
        else:
            sc = 0
        win32api.keybd_event(vk_code, sc, win32con.KEYEVENTF_KEYUP, 0)
    
    def key_press(self, key):
        self.key_down(key)
        time.sleep(0.1)
        self.key_up(key)
    
    def smooth_move_relative(self, dx: int, dy: int, duration=0.2):
        """
        平滑相对移动
        :param dx: x方向移动距离
        :param dy: y方向移动距离  
        :param duration: 移动总时长（秒）
        """
        # 根据距离自动调整步数
        distance = (dx**2 + dy**2) ** 0.5
        steps = max(10, int(distance / 20))  # 每20像素一步，最少10步
        
        step_x = dx / steps
        step_y = dy / steps
        delay = duration / steps
        
        for i in range(steps):
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(step_x), int(step_y))
            time.sleep(delay)
    
    def smooth_move_absolute(self, target_x: int, target_y: int, duration=0.2):
        """
        平滑绝对移动（从当前位置移动到目标位置）
        :param target_x: 目标屏幕x坐标
        :param target_y: 目标屏幕y坐标
        :param duration: 移动总时长（秒）
        """
        # 获取当前鼠标位置
        current_x, current_y = win32api.GetCursorPos()
        
        # 计算移动距离
        dx = target_x - current_x
        dy = target_y - current_y
        distance = (dx**2 + dy**2) ** 0.5
        
        # 如果距离很小，直接移动
        if distance < 20:
            win32api.SetCursorPos((target_x, target_y))
            return
        
        # 根据距离自动调整步数
        steps = max(2, int(distance / 20))  # 每20像素一步，最少2步
        delay = duration / steps
        
        # 分步移动
        for i in range(1, steps + 1):
            # 线性插值
            progress = i / steps
            intermediate_x = int(current_x + dx * progress)
            intermediate_y = int(current_y + dy * progress)
            win32api.SetCursorPos((intermediate_x, intermediate_y))
            time.sleep(delay)

    def move_to(self, x: int, y: int, resolution=None, anchor=ANCHOR_TOP_LEFT, relative=False, smooth=False):
        x = int(x)
        y = int(y)
        standard_w = 1920
        standard_h = 1080

        if resolution is not None:
            scale = resolution[1] / standard_w
        else:
            scale = 1

        if relative:
            x = int(x * scale)
            y = int(y * scale)
            if smooth:
                self.smooth_move_relative(x, y, duration=0.2)
            else:
                win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, x, y)
        else:
            if resolution is not None:
                actual_h = int(resolution[0] / scale)
            else:
                actual_h = standard_h
            if "TOP" in anchor:
                pass
            elif "BOTTOM" in anchor:
                y += actual_h - standard_h
            elif "CENTER" in anchor:
                y += (actual_h - standard_h) / 2
            else:
                pass

            x = int(x * scale)
            y = int(y * scale)
            screen_x, screen_y = win32gui.ClientToScreen(self.hwnd_handler.get_handle(), (x, y))
            
            if smooth:
                self.smooth_move_absolute(screen_x, screen_y, duration=0.2)
            else:
                win32api.SetCursorPos((screen_x, screen_y))

KEY_DOWN = 'KeyDown'
KEY_UP = 'KeyUp'

class Operation():

    def __str__(self):
        return f'Operation: {self.key} {self.type}'
    def __init__(self, key:str, type, operation_start=time.time(), operation_end = time.time()):
        self.key = key
        self.type = type
        self.operation_start = operation_start
        self.operation_end = operation_end
        self.operated = False


if __name__ == '__main__':
    if True:
        time.sleep(1)
        print('start test')
        itn = InteractionNormal()
        itn.move_to(1028, 150)
        # while 1:
        #     time.sleep(1)
        #     itn.left_click()
    