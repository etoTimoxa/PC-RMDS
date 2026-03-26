APP_STYLE = """
QMainWindow { background-color: #f5f5f5; }

QGroupBox {
    font-weight: bold;
    border: 2px solid #ff8c42;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: white;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px 0 5px;
    color: #ff8c42;
}

QLabel { color: #333333; }

QPushButton {
    background-color: #ff8c42;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton:hover { background-color: #ff6b2c; }
QPushButton:pressed { background-color: #e55a1a; }

QLineEdit, QTextEdit {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    padding: 5px;
}
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid #ff8c42;
}

QTabWidget::pane {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    background-color: white;
}
QTabBar::tab {
    background-color: #e0e0e0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #ff8c42;
    color: white;
}

QProgressBar {
    border: 1px solid #ff8c42;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #ff8c42;
    border-radius: 3px;
}

QStatusBar {
    background-color: #f0f0f0;
    color: #666666;
}

QSystemTrayIcon {
    color: #ff8c42;
}
"""