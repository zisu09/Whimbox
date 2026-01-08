from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from whimbox.common.logger import logger
from whimbox.task.background_task import background_manager, BackgroundFeature


# 功能按钮配置列表
FUNCTION_BUTTONS = [
    {
        'label': '启动游戏并一条龙',
        'task_name': 'all_in_one_task',
        'task_params': {},
        'start_message': '开始一条龙，按 / 结束任务\n',
    },
    {
        'label': '跑图路线',
        'task_name': 'load_path',
        'needs_dialog': True,  # 需要弹出对话框
        'dialog_type': 'path_selection',
    },
    {
        'label': '录制路线',
        'task_name': 'record_path',
        'task_params': {},
        'start_message': '开始录制路线，按 / 停止录制\n',
    },
    {
        'label': '宏脚本',
        'task_name': 'run_macro',
        'needs_dialog': True,  # 需要弹出对话框
        'dialog_type': 'macro_selection',
    },
    {
        'label': '录制宏',
        'task_name': 'record_macro',
        'task_params': {},
        'start_message': '开始录制宏，按 / 停止录制\n',
    }
]


class FunctionView(QWidget):
    """功能菜单视图组件"""
    # 统一的功能按钮点击信号
    function_clicked = pyqtSignal(dict)  # 传递按钮配置字典
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 按钮字典，key为button_id，value为QPushButton对象
        self.buttons = []
        
        # 后台任务相关
        self.background_checkboxes = {}  # 存储后台功能复选框
        
        # 初始化UI
        self.init_ui()
        
        # 从配置文件加载后台任务状态
        self._load_background_task_state()
    
    def init_ui(self):
        """初始化功能视图UI"""
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border: none;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: rgba(240, 240, 240, 150);
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #2196F3;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #1976D2;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 后台任务区域（固定在顶部，不滚动）
        background_container = self.create_background_task_section()
        layout.addWidget(background_container)
        
        # 创建滚动区域包装功能按钮
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        # 功能区域容器
        function_container = QWidget()
        function_container.setStyleSheet("""
            QWidget {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: rgba(240, 240, 240, 150);
            }
        """)
        
        function_layout = QVBoxLayout(function_container)
        function_layout.setContentsMargins(8, 8, 8, 8)
        function_layout.setSpacing(8)
        
        # 根据配置创建所有功能按钮
        # 第一个按钮独占一行
        button = self.create_function_button(FUNCTION_BUTTONS[0])
        self.buttons.append(button)
        function_layout.addWidget(button)
        
        # "自动跑图"和"录制路线"放在同一行
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(8)
        for config in FUNCTION_BUTTONS[1:3]:  # 索引 1, 2
            button = self.create_function_button(config)
            self.buttons.append(button)
            row1_layout.addWidget(button)
        function_layout.addLayout(row1_layout)
        
        # "运行宏"和"录制宏"放在同一行
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(8)
        for config in FUNCTION_BUTTONS[3:]:  # 索引 3, 4
            button = self.create_function_button(config)
            self.buttons.append(button)
            row2_layout.addWidget(button)
        function_layout.addLayout(row2_layout)
        
        # 添加弹性空间
        function_layout.addStretch()
        
        # 将功能容器放入滚动区域
        scroll_area.setWidget(function_container)
        layout.addWidget(scroll_area)
    
    def create_function_button(self, config: dict) -> QPushButton:
        """根据配置创建功能按钮"""
        button = QPushButton(config['label'])
        button.setFixedHeight(32)
        button.clicked.connect(lambda: self.on_function_button_clicked(config))
        button.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        return button
    
    def on_function_button_clicked(self, config: dict):
        """功能按钮点击统一处理"""
        logger.info(f"Function button clicked: {config['label']}")
        self.function_clicked.emit(config)
    
    def create_background_task_section(self) -> QWidget:
        """创建后台任务区域"""
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background-color: rgba(240, 240, 240, 150);
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 标题行
        title_layout = QHBoxLayout()
        title_layout.setSpacing(4)
        
        title = QLabel("自动小功能")
        title.setStyleSheet("""
            QLabel {
                font-size: 8pt;
                font-weight: bold;
                color: #000000;
                border: none;
                background-color: transparent;
            }
        """)
        title_layout.addWidget(title)

        sub_title = QLabel("觉得太慢了？可在设置中开启“高性能模式”")
        sub_title.setStyleSheet("""
            QLabel {
                font-size: 7pt;
                color: #666666;
                border: none;
                background-color: transparent;
            }
        """)
        title_layout.addWidget(sub_title)
        title_layout.addStretch()

        layout.addLayout(title_layout)
        
        # 功能复选框 - 每行两个
        feature_configs = [
            (BackgroundFeature.AUTO_FISHING, "自动钓鱼"),
            (BackgroundFeature.AUTO_DIALOGUE, "自动对话"),
            (BackgroundFeature.AUTO_PICKUP, "自动采集"),
            (BackgroundFeature.AUTO_CLEAR, "自动清洁跳过"),
            (BackgroundFeature.AUTO_FLOURISH, "自动芳间巡游（按鼠标右键启停）"),
        ]
        
        # 创建网格布局，每行2个
        for i in range(0, len(feature_configs), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(12)
            
            # 第一个复选框
            feature1, label1 = feature_configs[i]
            checkbox1 = self._create_checkbox(feature1, label1)
            row_layout.addWidget(checkbox1)
            
            # 第二个复选框（如果存在）
            if i + 1 < len(feature_configs):
                feature2, label2 = feature_configs[i + 1]
                checkbox2 = self._create_checkbox(feature2, label2)
                row_layout.addWidget(checkbox2)
            else:
                row_layout.addStretch()
            
            layout.addLayout(row_layout)
        
        return container
    
    def _create_checkbox(self, feature: BackgroundFeature, label: str) -> QCheckBox:
        """创建复选框"""
        checkbox = QCheckBox(label)
        checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 8pt;
                color: #000000;
                border: none;
                spacing: 4px;
                background-color: transparent;
            }
        """)
        checkbox.stateChanged.connect(
            lambda state, f=feature: self.on_background_feature_changed(f, state == Qt.Checked)
        )
        self.background_checkboxes[feature] = checkbox
        return checkbox
    
    def on_background_feature_changed(self, feature: BackgroundFeature, enabled: bool):
        """后台功能复选框改变 - 直接调用 background_manager"""
        try:
            # 直接调用 background_manager 设置功能
            background_manager.set_feature_enabled(feature, enabled)
            
            # 检查是否需要启动或停止后台任务
            any_enabled = any(
                background_manager.is_feature_enabled(f) 
                for f in BackgroundFeature
            )
            
            if any_enabled and not background_manager.is_running():
                # 有功能启用但任务未运行，启动任务
                background_manager.start_background_task()
            elif not any_enabled and background_manager.is_running():
                # 没有功能启用但任务在运行，停止任务
                background_manager.stop_background_task()
            
            logger.info(f"后台功能设置成功: {feature.value} = {enabled}")
            
        except Exception as e:
            # 设置失败，恢复复选框状态
            logger.error(f"后台功能设置失败: {e}")
            checkbox = self.background_checkboxes[feature]
            checkbox.blockSignals(True)
            checkbox.setChecked(not enabled)
            checkbox.blockSignals(False)
    
    def set_all_buttons_enabled(self, enabled: bool):
        """设置所有按钮是否可用"""
        for button in self.buttons:
            button.setEnabled(enabled)
    
    def _load_background_task_state(self):
        """直接从 background_manager 加载后台任务状态"""
        try:
            # 阻止信号触发，避免触发状态修改
            for checkbox in self.background_checkboxes.values():
                checkbox.blockSignals(True)
            
            # 直接从 background_manager 读取状态
            for feature, checkbox in self.background_checkboxes.items():
                enabled = background_manager.is_feature_enabled(feature)
                checkbox.setChecked(enabled)
                logger.info(f"加载后台任务状态: {feature.value}={enabled}")
            
            # 恢复信号
            for checkbox in self.background_checkboxes.values():
                checkbox.blockSignals(False)
                
        except Exception as e:
            logger.error(f"加载后台任务状态失败: {e}")

