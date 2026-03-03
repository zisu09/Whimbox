import threading
import time

from whimbox.common import timer_module
import numpy as np
import win32ui
import cv2
import win32gui
import ctypes
from whimbox.common.logger import logger
from whimbox.common.cvars import DEBUG_MODE


class Capture():
    def __init__(self, hwnd_handler):
        self.hwnd_handler = hwnd_handler
        self.capture_cache = np.zeros_like((1080,1920,3), dtype="uint8")
        self.resolution = None
        self.max_fps = 30
        self.fps_timer = timer_module.Timer(diff_start_time=1)
        self.capture_cache_lock = threading.Lock()
        self.capture_times = 0
        self.cap_per_sec = timer_module.CyclicCounter(limit=3).start()
        self.last_cap_times = 0

    def _cover_privacy(self, img: np.ndarray) -> np.ndarray:
        return img

    def _normalize_shape(self, img: np.ndarray) -> np.ndarray:
        if self._check_shape(img):
            self.resolution = img.shape[:2]
            if img.shape == (1080,1920,4):
                return img
            else:
                new_width = 1920
                new_height = int(1920 / self.resolution[1] * self.resolution[0])
                new_img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
                return new_img
        else:
            self.resolution = None
            return None
    
    def _get_capture(self) -> np.ndarray:
        """
        需要根据不同截图方法实现该函数。
        """
    
    def _check_shape(self, img:np.ndarray):
        return True
        
    def capture(self, force=False) -> np.ndarray:
        """
        供外部调用的截图接口

        Args:
            force: 无视帧率限制，强制截图
        """
        if DEBUG_MODE:
            r = self.cap_per_sec.count_times()
            if r:
                if r != self.last_cap_times:
                    logger.trace(f"capps: {r/3}")
                    self.last_cap_times = r
                elif r >= 10*3:
                    logger.trace(f"capps: {r/3}")
                elif r >= 20*3:
                    logger.debug(f"capps: {r/3}")
                elif r >= 40*3:
                    logger.info(f"capps: {r/3}")
        with self.capture_cache_lock:
            self._capture(force)
            cp = self.capture_cache.copy()
        return cp
    
    def _capture(self, force) -> None:
        if (self.fps_timer.get_diff_time() >= 1/self.max_fps) or force:
            self.fps_timer.reset()
            self.capture_times += 1
            if self.hwnd_handler.is_alive():
                normalized_img = self._normalize_shape(self._get_capture())
                if normalized_img is not None:
                    self.capture_cache = normalized_img

    
class PrintWindowCapture(Capture):
    def __init__(self, hwnd_handler):
        super().__init__(hwnd_handler)
        self.max_fps = 30

    def _check_shape(self, img:np.ndarray):
        if img.shape[2] == 4 and img.shape[1] > 0 and 1.55<img.shape[1]/img.shape[0]<1.80:
            # 支持16:9和16:10分辨率
            # 有些用户在特定显示器和缩放下会生成奇怪的1920x1081分辨率，增加宽容度
            return True
        else:
            logger.info("游戏分辨率异常: "+str(img.shape))
            return False

    def _get_capture(self):
        hwnd = self.hwnd_handler.get_handle()
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bottom - top

        hdc_window = win32gui.GetWindowDC(hwnd)
        hdc_mem = win32ui.CreateDCFromHandle(hdc_window)
        hdc_compat = hdc_mem.CreateCompatibleDC()

        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc_mem, width, height)
        hdc_compat.SelectObject(bmp)

        result = ctypes.windll.user32.PrintWindow(hwnd, hdc_compat.GetSafeHdc(), 3)

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8)
        img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)

        win32gui.DeleteObject(bmp.GetHandle())
        hdc_compat.DeleteDC()
        hdc_mem.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc_window)
        
        return img


if __name__ == '__main__':
    c = PrintWindowCapture()
    while 1:
        cv2.imshow("capture test", c.capture())
        cv2.waitKey(10)
        # time.sleep(0.01)
