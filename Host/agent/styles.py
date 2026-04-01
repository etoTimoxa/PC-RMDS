def get_main_window_stylesheet():
    """Возвращает базовые стили для главного окна"""
    return """
    QMainWindow { background-color: #f5f5f5; }
    QWidget { background-color: #f5f5f5; }
    
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
    
    QPushButton#settingsButton {
        background-color: rgba(255,255,255,0.2);
        color: white;
        font-size: 20px;
        border-radius: 20px;
        padding: 0px;
        margin: 0px;
        font-weight: normal;
    }
    
    QLineEdit, QTextEdit {
        border: 1px solid #ff8c42;
        border-radius: 4px;
        padding: 5px;
        background-color: white;
    }
    
    QTableWidget {
        border: 1px solid #ddd;
        border-radius: 4px;
        background-color: white;
    }
    QTableWidget::item {
        padding: 5px;
    }
    QTableWidget::item:selected {
        background-color: #ff8c42;
        color: white;
    }
    QHeaderView::section {
        background-color: #f0f0f0;
        padding: 8px;
        border: none;
        border-bottom: 2px solid #ff8c42;
        font-weight: bold;
    }
    
    QStatusBar {
        background-color: #f0f0f0;
        color: #666666;
    }
    """


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

QPushButton#settingsButton {
    background-color: rgba(255,255,255,0.2);
    color: white;
    font-size: 20px;
    border-radius: 20px;
    padding: 0px;
    margin: 0px;
    font-weight: normal;
}
QPushButton#settingsButton:hover { 
    background-color: rgba(255,255,255,0.3); 
}
QPushButton#settingsButton:pressed { 
    background-color: rgba(255,255,255,0.4); 
}

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