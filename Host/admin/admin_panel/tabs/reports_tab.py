from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame)
from PyQt6.QtCore import Qt


class ReportsTab(QWidget):
    """Вкладка с отчетами"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        
        label = QLabel("📊 Модуль отчетов в разработке")
        label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #7f8c8d;
        """)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        frame_layout.addWidget(label)
        layout.addWidget(frame)