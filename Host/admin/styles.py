def get_main_window_stylesheet():
    """Возвращает стили для главного окна (оранжево-белый дизайн)"""
    return """
    /* Основные цвета */
    QMainWindow { 
        background-color: #f8f9fa; 
    }
    
    QWidget { 
        background-color: #f8f9fa; 
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    /* Кнопки */
    QPushButton {
        background-color: #ff8c42;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 13px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QPushButton:hover { 
        background-color: #e67e22; 
    }
    
    QPushButton:pressed { 
        background-color: #d35400; 
    }
    
    QPushButton:disabled {
        background-color: #bdc3c7;
    }
    
    /* Поля ввода */
    QLineEdit, QTextEdit, QDateEdit, QComboBox {
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 8px 10px;
        background-color: white;
        font-size: 13px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QComboBox:focus {
        border: 2px solid #ff8c42;
    }
    
    /* Таблицы */
    QTableWidget {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: white;
        alternate-background-color: #fafafa;
        gridline-color: #f0f0f0;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QTableWidget::item {
        padding: 10px;
    }
    
    QTableWidget::item:selected {
        background-color: #ff8c42;
        color: white;
    }
    
    QHeaderView::section {
        background-color: #f8f9fa;
        padding: 10px;
        border: none;
        border-bottom: 2px solid #ff8c42;
        font-weight: bold;
        font-size: 12px;
        color: #2c3e50;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    /* Группы */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 12px;
        background-color: white;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 15px;
        padding: 0 8px;
        color: #ff8c42;
    }
    
    /* Статус бар */
    QStatusBar {
        background-color: #ffffff;
        color: #7f8c8d;
        border-top: 1px solid #e0e0e0;
        padding: 5px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    /* Скроллбары */
    QScrollBar:vertical {
        border: none;
        background-color: #f0f0f0;
        width: 10px;
        border-radius: 5px;
    }
    
    QScrollBar::handle:vertical {
        background-color: #ff8c42;
        border-radius: 5px;
        min-height: 30px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: #e67e22;
    }
    
    QScrollBar:horizontal {
        border: none;
        background-color: #f0f0f0;
        height: 10px;
        border-radius: 5px;
    }
    
    QScrollBar::handle:horizontal {
        background-color: #ff8c42;
        border-radius: 5px;
        min-width: 30px;
    }
    
    QScrollBar::handle:horizontal:hover {
        background-color: #e67e22;
    }
    
    /* Вкладки */
    QTabWidget::pane {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: white;
    }
    
    QTabBar::tab {
        background-color: #f0f0f0;
        padding: 10px 24px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: bold;
        color: #7f8c8d;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QTabBar::tab:selected {
        background-color: #ff8c42;
        color: white;
    }
    
    QTabBar::tab:hover:!selected {
        background-color: #e0e0e0;
        color: #2c3e50;
    }
    
    /* Прогресс бар */
    QProgressBar {
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        text-align: center;
        background-color: white;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QProgressBar::chunk {
        background-color: #ff8c42;
        border-radius: 5px;
    }
    
    /* Меню */
    QMenu {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 5px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QMenu::item {
        padding: 8px 20px;
        border-radius: 4px;
    }
    
    QMenu::item:selected {
        background-color: #ff8c42;
        color: white;
    }
    
    /* Системный трей */
    QSystemTrayIcon {
        color: #ff8c42;
    }
    
    /* Спинбоксы */
    QSpinBox, QDoubleSpinBox {
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 5px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    /* Чекбоксы */
    QCheckBox {
        spacing: 8px;
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
        background-color: white;
    }
    
    QCheckBox::indicator:checked {
        background-color: #ff8c42;
        border-color: #ff8c42;
    }
    
    /* Метки */
    QLabel {
        font-family: 'Microsoft YaHei', 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    """


APP_STYLE = get_main_window_stylesheet()