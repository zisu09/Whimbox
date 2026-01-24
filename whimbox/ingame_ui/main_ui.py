import win32gui
import win32con
import win32process
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from pynput import keyboard
import sys
import ctypes
from ctypes.wintypes import MSG
from importlib.metadata import version, PackageNotFoundError

from whimbox.common.handle_lib import HANDLE_OBJ
from whimbox.common.logger import logger
from whimbox.config.config import global_config

from whimbox.ingame_ui.components import SettingsDialog, ChatView, PathSelectionDialog, MacroSelectionDialog, FunctionView
from whimbox.ingame_ui.workers.call_worker import TaskCallWorker

update_time = 500  # ui更新间隔，ms

class IngameUI(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. 立即加载并设置位置/大小，防止启动闪烁
        pos_x = global_config.get_int("General", "windows_pos_x", 10)
        pos_y = global_config.get_int("General", "windows_pos_y", 10)
        self.saved_position = QPoint(pos_x, pos_y)
        self.move(self.saved_position) 
        
        saved_width = global_config.get_int("General", "ui_width", 500)
        saved_height = global_config.get_int("General", "ui_height", 600)
        self.saved_size = QSize(saved_width, saved_height)
        self.resize(self.saved_size)
        
        # 2. 状态管理
        self.is_expanded = True
        self.task_running = False
        self.ui_clickable = True
        self.current_view = 'chat'
        self.waiting_for_task_stop = False
        
        # UI组件初始化
        self.chat_view = None
        self.function_view = None
        self.view_toggle_button = None
        self.title_label = None
        self.task_worker = None
        self.settings_dialog = None
        self.path_dialog = None
        self.macro_dialog = None
        
        # 缩放边缘宽度
        self.resize_margin = 10
        
        # 3. 初始化UI
        self.init_ui()
        
        # 4. 计时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui_focus)
        self.timer.start(update_time)

        # 5. 窗口系统设置
        self.setWindowTitle("奇想盒")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # 设置窗口样式以支持任务栏交互
        hwnd = int(self.winId())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        # 确保窗口有最小化按钮样式
        style |= win32con.WS_MINIMIZEBOX
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        
        # 6. 获取焦点
        self.acquire_focus()
        
        # 键盘监听
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.daemon = True
        self.listener.start()

    def on_key_press(self, key):
        if key == keyboard.KeyCode.from_char('/'):
            QTimer.singleShot(0, self.on_slash_pressed)
        elif key == keyboard.Key.esc:
            QTimer.singleShot(0, self.on_esc_pressed)
    
    def init_ui(self):
        """初始化UI组件"""
        # 设置窗口基本属性
        self.setMinimumSize(200, 250)
        self.setObjectName("IngameUI")
        self.setMouseTracking(True)
        
        # 主窗口布局（提供缩放边缘的 margin）
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. 创建背景容器 (使用 QFrame，它原生支持样式表)
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("bgFrame")
        self.outer_layout.addWidget(self.bg_frame)
        
        # 2. 容器内部布局
        self.main_layout = QVBoxLayout(self.bg_frame)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(2)
        
        # 初始样式
        self.update_focus_visual(False)
        
        # 标题栏
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignVCenter)
        self.title_label = QLabel("⚪ 📦 奇想盒 [按 / 激活窗口]")
        self.title_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                font-size: 8pt;
                font-weight: bold; 
                border: none; 
            }
        """)

        # 版本号标签
        try:
            app_version = version("whimbox")
        except PackageNotFoundError:
            app_version = "dev"
        
        version_label = QLabel(app_version)
        version_label.setStyleSheet("""
            QLabel {
                background-color: #E3F2FD;
                color: #1976D2;
                font-size: 6pt;
                font-weight: bold;
                padding: 1px 4px;
                border-radius: 5px;
                border: 1px solid #2196F3;
                margin-top: 2px;
            }
        """)
        version_label.setFixedHeight(16)
        
        settings_button = QPushButton("⚙️")
        settings_button.setFixedSize(16, 16)
        settings_button.clicked.connect(self.open_settings)
        settings_button.setStyleSheet("""
            QPushButton {
                background-color: #E3F2FD;
                border: 1px solid #2196F3;
                font-size: 6pt;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        
        minimize_button = QPushButton("➖")
        minimize_button.setFixedSize(16, 16)
        minimize_button.clicked.connect(self.toggle_minimize)
        minimize_button.setStyleSheet("""
            QPushButton {
                background-color: #FFF9C4;
                border: 1px solid #FBC02D;
                font-size: 6pt;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #F9A825;
            }
        """)

        close_button = QPushButton("❌")
        close_button.setFixedSize(16, 16)
        close_button.clicked.connect(self.close_application)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #FFEBEE;
                border: 1px solid #F44336;
                font-size: 6pt;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(version_label)
        title_layout.addStretch()
        title_layout.addWidget(settings_button)
        title_layout.addWidget(minimize_button)
        title_layout.addWidget(close_button)
        
        # 视图切换按钮
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 2, 0, 2)
        
        self.view_toggle_button = QPushButton("🎯 功能菜单")
        self.view_toggle_button.setFixedHeight(32)
        self.view_toggle_button.clicked.connect(self.toggle_view)
        self.view_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        
        button_layout.addWidget(self.view_toggle_button)
        
        # 创建组件
        self.function_view = FunctionView(self)
        self.function_view.function_clicked.connect(self.on_function_clicked)
        
        self.chat_view = ChatView(self)
        self.chat_view.request_focus.connect(self.on_agent_task_request_focus)
        self.chat_view.release_focus.connect(self.on_agent_task_release_focus)
        
        # 组装布局
        self.main_layout.addLayout(title_layout)
        self.main_layout.addLayout(button_layout)
        self.main_layout.addWidget(self.function_view, 1)
        self.main_layout.addWidget(self.chat_view, 1)
        
        # 默认显示聊天视图
        self.function_view.hide()
        
        # 添加欢迎消息
        if self.chat_view and not self.chat_view.has_messages():
            self.chat_view.add_message("👋 您好！我是奇想盒📦，你可以直接选择功能，或者和我聊天。", 'ai')

    def toggle_view(self):
        """切换视图（功能菜单 <-> 对话框）"""
        if self.current_view == 'function':
            self.current_view = 'chat'
            self.function_view.hide()
            self.chat_view.show()
            self.view_toggle_button.setText("🎯 功能菜单")
            logger.info("Switched to chat view")
        else:
            self.current_view = 'function'
            self.chat_view.hide()
            self.function_view.show()
            self.view_toggle_button.setText("💬 返回对话框")
            logger.info("Switched to function view")
    
    def switch_to_chat_view(self):
        """切换到聊天视图"""
        if self.current_view != 'chat':
            self.current_view = 'chat'
            self.function_view.hide()
            self.chat_view.show()
            self.view_toggle_button.setText("🎯 功能菜单")
            logger.info("Switched to chat view")
    
    def on_function_clicked(self, config: dict):
        """统一处理功能按钮点击"""
        if self.task_worker and self.task_worker.isRunning():
            self.chat_view.add_message("已有任务正在运行中，请稍候...", "ai")
            self.switch_to_chat_view()
            return
        
        self.switch_to_chat_view()
        
        if config.get('needs_dialog'):
            if config['dialog_type'] == 'path_selection':
                self.path_dialog = PathSelectionDialog(self)
                self.path_dialog.path_selected.connect(lambda path: self.start_task_with_path(config, path))
                self.path_dialog.show_centered()
                self.path_dialog.exec_()
            elif config['dialog_type'] == 'macro_selection':
                self.macro_dialog = MacroSelectionDialog(self, is_play_music=config.get('is_play_music', False))
                self.macro_dialog.macro_selected.connect(lambda macro: self.start_task_with_macro(config, macro))
                self.macro_dialog.show_centered()
                self.macro_dialog.exec_()
        else:
            self.start_task(config)
    
    def start_task(self, config: dict):
        self.give_back_focus(title_text="⚪ 📦 奇想盒 [任务运行中，按 / 结束任务]")
        if self.function_view:
            self.function_view.set_all_buttons_enabled(False)
        if self.chat_view and config.get('start_message'):
            self.chat_view.add_message(config['start_message'], 'ai')
        
        self.task_worker = TaskCallWorker(config['task_name'], config.get('task_params', {}))
        self.task_worker.progress.connect(self.on_task_progress)
        self.task_worker.finished.connect(self.on_task_finished)
        self.task_worker.start()
        self.task_running = True
    
    def start_task_with_path(self, config: dict, path_name: str):
        self.give_back_focus(title_text="⚪ 📦 奇想盒 [任务运行中，按 / 结束任务]")
        if self.function_view:
            self.function_view.set_all_buttons_enabled(False)
        if self.chat_view:
            self.chat_view.add_message(f'开始自动跑图：{path_name}，按 / 结束任务\n', 'ai')
        
        params = dict(config.get('task_params', {}))
        params['path_name'] = path_name
        self.task_worker = TaskCallWorker(config['task_name'], params)
        self.task_worker.progress.connect(self.on_task_progress)
        self.task_worker.finished.connect(self.on_task_finished)
        self.task_worker.start()
        self.task_running = True
    
    def start_task_with_macro(self, config: dict, macro_name: str):
        self.give_back_focus(title_text="⚪ 📦 奇想盒 [任务运行中，按 / 结束任务]")
        if self.function_view:
            self.function_view.set_all_buttons_enabled(False)
        if self.chat_view:
            self.chat_view.add_message(config['start_message'].format(macro_name=macro_name), 'ai')
        
        params = dict(config.get('task_params', {}))
        params['macro_name'] = macro_name
        self.task_worker = TaskCallWorker(config['task_name'], params)
        self.task_worker.progress.connect(self.on_task_progress)
        self.task_worker.finished.connect(self.on_task_finished)
        self.task_worker.start()
        self.task_running = True
    
    def on_task_progress(self, message: str):
        logger.info(f"Task progress: {message}")
        if self.chat_view:
            self.chat_view.add_message(message, 'ai')
    
    def on_task_finished(self, success: bool, result):
        if self.function_view:
            self.function_view.set_all_buttons_enabled(True)
        if success:
            if self.chat_view:
                self.chat_view.add_message(f"✅ 任务完成: {result['message']}", 'ai')
        else:
            if self.chat_view:
                self.chat_view.add_message(f"❌ 任务失败：{result['message']}", 'error')
        if self.task_worker:
            self.task_worker.deleteLater()
            self.task_worker = None
        if self.waiting_for_task_stop:
            self.waiting_for_task_stop = False
            self.expand_chat()
        else:
            self.acquire_focus()
        self.task_running = False
    
    def on_agent_task_release_focus(self, title_text: str):
        self.give_back_focus(title_text)
        self.task_running = True
    
    def on_agent_task_request_focus(self):
        if self.waiting_for_task_stop:
            self.waiting_for_task_stop = False
            self.expand_chat()
        else:
            self.acquire_focus()
        self.task_running = False
    
    def nativeEvent(self, eventType, message):
        event_str = str(eventType)
        if "windows_generic_msg" in event_str.lower():
            msg = MSG.from_address(int(message))
            
            # 处理窗口大小调整和拖动
            if msg.message == win32con.WM_NCHITTEST:
                pos = self.mapFromGlobal(QCursor.pos())
                
                margin = self.resize_margin
                w, h = self.width(), self.height()
                lx = pos.x() < margin
                rx = pos.x() > w - margin
                ty = pos.y() < margin
                by = pos.y() > h - margin
                
                if lx and ty: return True, win32con.HTTOPLEFT
                if rx and ty: return True, win32con.HTTOPRIGHT
                if lx and by: return True, win32con.HTBOTTOMLEFT
                if rx and by: return True, win32con.HTBOTTOMRIGHT
                if lx: return True, win32con.HTLEFT
                if rx: return True, win32con.HTRIGHT
                if ty: return True, win32con.HTTOP
                if by: return True, win32con.HTBOTTOM
                
                if pos.y() < 60:
                    child = self.childAt(pos)
                    if not child or not isinstance(child, (QPushButton, QLineEdit, QTextEdit)):
                        return True, win32con.HTCAPTION
            
            # 处理系统命令（包括任务栏图标点击）
            elif msg.message == win32con.WM_SYSCOMMAND:
                command = msg.wParam & 0xFFF0
                # SC_RESTORE: 还原窗口（从最小化状态）
                if command == win32con.SC_RESTORE:
                    if self.isMinimized():
                        self.showNormal()
                        self.activateWindow()
                        self.raise_()
                        return True, 0
                # SC_MINIMIZE: 最小化窗口
                elif command == win32con.SC_MINIMIZE:
                    self.showMinimized()
                    return True, 0
                        
        return super().nativeEvent(eventType, message)

    def moveEvent(self, event):
        super().moveEvent(event)
        new_pos = self.pos()
        if self.saved_position != new_pos:
            self.saved_position = new_pos
            global_config.set("General", "windows_pos_x", new_pos.x())
            global_config.set("General", "windows_pos_y", new_pos.y())
            global_config.save()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isActiveWindow():
            new_size = self.size()
            global_config.set("General", "ui_width", new_size.width())
            global_config.set("General", "ui_height", new_size.height())
            global_config.save()
    
    def changeEvent(self, event):
        """处理窗口状态变化事件"""
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                logger.info("Window minimized")
            elif event.oldState() & Qt.WindowMinimized:
                # 从最小化状态恢复
                logger.info("Window restored from minimized state")
        elif event.type() == QEvent.WindowActivate:
            # 窗口被激活
            logger.info("Window activated")
        elif event.type() == QEvent.WindowDeactivate:
            # 窗口失去激活状态
            logger.info("Window deactivated")
        super().changeEvent(event)
        
    def expand_chat(self):
        logger.info("Expanding chat interface")
        self.position_window()
        # 如果窗口被最小化，先还原
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.acquire_focus()
        QTimer.singleShot(100, lambda: self.chat_view.set_focus_to_input() if self.chat_view else None)
    
    def toggle_minimize(self):
        """切换窗口最小化/还原状态"""
        if self.isMinimized():
            # 还原窗口
            self.showNormal()
            self.activateWindow()
            self.raise_()
        else:
            # 最小化窗口
            self.showMinimized()
    
    def close_application(self):
        reply = QMessageBox.question(self, '确认关闭', '确定要关闭奇想盒吗？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            logger.info("User confirmed - closing whimbox")
            sys.exit(0)
    
    def open_settings(self):
        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show_centered()
        self.settings_dialog.exec_()
    
    def update_focus_visual(self, has_focus: bool, title_text: str = "⚪ 📦 奇想盒 [按 / 激活窗口]"):
        if not hasattr(self, 'bg_frame') or not self.bg_frame:
            return
            
        if has_focus:
            self.bg_frame.setStyleSheet("""
                #bgFrame {
                    background-color: rgba(255, 255, 255, 120);
                    border-radius: 12px;
                    border: 1px solid #2196F3;
                }
            """)
            if self.title_label:
                self.title_label.setText("🟢 📦 奇想盒")
        else:
            self.bg_frame.setStyleSheet("""
                #bgFrame {
                    background-color: rgba(255, 255, 255, 120);
                    border-radius: 12px;
                    border: 1px solid #E0E0E0;
                }
            """)
            if self.title_label:
                self.title_label.setText(title_text)

    def acquire_focus(self):
        hwnd = int(self.winId())
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & ~win32con.WS_EX_TRANSPARENT)
        # # 如果窗口被最小化，先还原
        # if self.isMinimized():
        #     self.showNormal()
        
        # 使用 Windows API 的技巧来获取焦点 - 附加到前台窗口的线程
        try:
            foreground_hwnd = win32gui.GetForegroundWindow()
            if foreground_hwnd != hwnd:
                # 获取前台窗口的线程ID
                foreground_thread = win32process.GetWindowThreadProcessId(foreground_hwnd)[0]
                # 获取当前窗口的线程ID
                current_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
                
                # 附加到前台窗口的线程，这样可以绕过 SetForegroundWindow 的限制
                if foreground_thread != current_thread:
                    ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True)
                
                # 现在设置前台窗口
                win32gui.SetForegroundWindow(hwnd)
                win32gui.BringWindowToTop(hwnd)
                
                # 分离线程
                if foreground_thread != current_thread:
                    ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)
                
                logger.info(f"Set UI window as foreground: {hwnd}")
        except Exception as e:
            logger.warning(f"Failed to set foreground window: {e}")
        
        self.ui_clickable = True
        self.update_focus_visual(True)

    def give_back_focus(self, title_text: str = "⚪ 📦 奇想盒 [按 / 激活窗口]"):
        hwnd = int(self.winId())
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_TRANSPARENT)
        self.ui_clickable = False
        HANDLE_OBJ.set_foreground()
        self.update_focus_visual(False, title_text)

    def position_window(self):
        self.move(self.saved_position)

    def on_slash_pressed(self):
        # if win32gui.GetForegroundWindow() != HANDLE_OBJ.get_handle():
        #     return
        if self.waiting_for_task_stop:
            return
        has_manual_task = self.task_worker and self.task_worker.isRunning()
        has_agent_task = self.chat_view and self.chat_view.current_worker and self.chat_view.current_worker.isRunning()
        if has_manual_task or has_agent_task:
            self.waiting_for_task_stop = True
            self.update_focus_visual(False, "⚪ 📦 奇想盒 [等待任务结束中…]")
            logger.info("Waiting for task to stop...")
        else:
            self.expand_chat()
    
    def on_esc_pressed(self):
        if win32gui.GetForegroundWindow() != int(self.winId()):
            return
        self.toggle_minimize()
    
    def update_ui_focus(self):
        if (not self.isMinimized()) and (not self.task_running):
            game_is_foreground = HANDLE_OBJ.is_foreground()
            
            # 原逻辑：如果游戏是前台且UI可点击，把焦点还给游戏
            # 但现在加上检查：只有当UI确实不是前台时才还焦点
            if game_is_foreground and self.ui_clickable:
                self.give_back_focus()
            # 原逻辑：如果游戏不是前台且UI不可点击，获取焦点
            elif not game_is_foreground and not self.ui_clickable:
                self.acquire_focus()
    
    def update_message(self, message: str, type="update_ai_message"):
        if self.chat_view:
            self.chat_view.ui_update_signal.emit(type, message)
