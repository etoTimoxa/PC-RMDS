import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTableWidget,
                             QTableWidgetItem, QHeaderView, QTabWidget,
                             QDateEdit, QGroupBox, QApplication, QComboBox,
                             QGridLayout, QScrollArea, QMessageBox,
                             QCalendarWidget, QDialog, QDialogButtonBox,
                             QProgressBar, QLineEdit, QTextEdit, QFormLayout,
                             QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFont

from core.api_client import APIClient
from .styles import get_main_window_stylesheet

# Попытка импортировать matplotlib для графиков
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Matplotlib не установлен. Графики будут недоступны.")

# Попытка импортировать reportlab для PDF
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("ReportLab не установлен. Экспорт в PDF будет недоступен.")


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    from pathlib import Path
    
    icon_path = Path(__file__).parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    icon_path = Path(__file__).parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    icon_path = Path.cwd() / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    icon_path = Path.cwd() / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(255, 140, 66))
    return QIcon(pixmap)


class DiskSpaceWidget(QWidget):
    """Виджет для отображения свободного места на диске с прогресс-баром"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel("Свободное место на диске")
        self.title_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.title_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                text-align: center;
                height: 20px;
                background-color: white;
            }
            QProgressBar::chunk {
                background-color: #ff8c42;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.info_label = QLabel("Загрузка...")
        self.info_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(self.info_label)
    
    def update_disk_info(self, used_gb, total_gb):
        if used_gb and total_gb and total_gb > 0:
            free_gb = total_gb - used_gb
            used_percent = (used_gb / total_gb) * 100
            free_percent = 100 - used_percent
            
            self.progress_bar.setValue(int(used_percent))
            self.progress_bar.setFormat(f"Занято: {used_percent:.1f}%")
            
            self.info_label.setText(f"Свободно: {free_gb:.1f} GB из {total_gb:.1f} GB ({free_percent:.1f}%)")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Нет данных")
            self.info_label.setText("Нет данных о диске")


class EditComputerDialog(QDialog):
    """Диалог для редактирования информации о компьютере"""
    
    def __init__(self, computer_data, computer_id, parent=None):
        super().__init__(parent)
        self.computer_data = computer_data
        self.computer_id = computer_id
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Редактирование компьютера")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Форма
        form_layout = QFormLayout()
        
        # Hostname
        self.hostname_edit = QLineEdit()
        self.hostname_edit.setText(self.computer_data.get('hostname', ''))
        form_layout.addRow("Hostname:", self.hostname_edit)
        
        # Описание
        self.description_edit = QTextEdit()
        self.description_edit.setText(self.computer_data.get('description', ''))
        self.description_edit.setMaximumHeight(80)
        form_layout.addRow("Описание:", self.description_edit)
        
        # Расположение
        self.location_edit = QLineEdit()
        self.location_edit.setText(self.computer_data.get('location', ''))
        form_layout.addRow("Расположение:", self.location_edit)
        
        # Отдел
        self.department_edit = QLineEdit()
        self.department_edit.setText(self.computer_data.get('department', ''))
        form_layout.addRow("Отдел:", self.department_edit)
        
        # Инвентарный номер
        self.inventory_edit = QLineEdit()
        self.inventory_edit.setText(self.computer_data.get('inventory_number', ''))
        form_layout.addRow("Инвентарный номер:", self.inventory_edit)
        
        # Тип компьютера
        self.type_combo = QComboBox()
        self.type_combo.addItems(["client", "admin", "server"])
        current_type = self.computer_data.get('computer_type', 'client')
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        form_layout.addRow("Тип:", self.type_combo)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def save(self):
        """Сохраняет изменения"""
        data = {}
        
        if self.hostname_edit.text() != self.computer_data.get('hostname', ''):
            data['hostname'] = self.hostname_edit.text()
        
        if self.description_edit.toPlainText() != self.computer_data.get('description', ''):
            data['description'] = self.description_edit.toPlainText()
        
        if self.location_edit.text() != self.computer_data.get('location', ''):
            data['location'] = self.location_edit.text()
        
        if self.department_edit.text() != self.computer_data.get('department', ''):
            data['department'] = self.department_edit.text()
        
        if self.inventory_edit.text() != self.computer_data.get('inventory_number', ''):
            data['inventory_number'] = self.inventory_edit.text()
        
        if self.type_combo.currentText() != self.computer_data.get('computer_type', 'client'):
            data['computer_type'] = self.type_combo.currentText()
        
        if data:
            self.accept()
            self.update_data = data
        else:
            self.reject()
    
    def get_update_data(self):
        return getattr(self, 'update_data', {})


class EditSessionDialog(QDialog):
    """Диалог для просмотра информации о сессии"""
    
    def __init__(self, session_data, parent=None):
        super().__init__(parent)
        self.session_data = session_data
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle(f"Информация о сессии #{self.session_data.get('session_id', '')}")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Информация о сессии
        info_group = QGroupBox("Детали сессии")
        info_layout = QFormLayout(info_group)
        
        info_layout.addRow("ID сессии:", QLabel(str(self.session_data.get('session_id', '—'))))
        info_layout.addRow("Токен:", QLabel(self.session_data.get('session_token', '—')[:50] + "..."))
        info_layout.addRow("Статус:", QLabel(self.session_data.get('status_name', '—')))
        info_layout.addRow("Начало:", QLabel(str(self.session_data.get('start_time', '—'))[:19]))
        
        end_time = self.session_data.get('end_time')
        if end_time:
            info_layout.addRow("Окончание:", QLabel(str(end_time)[:19]))
        else:
            info_layout.addRow("Окончание:", QLabel("Активна"))
        
        info_layout.addRow("Последняя активность:", QLabel(str(self.session_data.get('last_activity', '—'))[:19]))
        info_layout.addRow("Отправлено JSON:", QLabel(str(self.session_data.get('json_sent_count', 0))))
        info_layout.addRow("Ошибок:", QLabel(str(self.session_data.get('error_count', 0))))
        
        layout.addWidget(info_group)
        
        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class DateRangeDialog(QDialog):
    """Диалог для выбора диапазона дат с двумя календарями"""
    
    def __init__(self, parent=None, start_date=None, end_date=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор периода")
        self.setModal(True)
        self.setMinimumSize(650, 450)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("Выберите диапазон дат")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff8c42; padding: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        calendar_layout = QHBoxLayout()
        calendar_layout.setSpacing(20)
        
        from_group = QGroupBox("Дата начала")
        from_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ff8c42;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ff8c42;
            }
        """)
        from_layout = QVBoxLayout(from_group)
        self.from_calendar = QCalendarWidget()
        self.from_calendar.setGridVisible(True)
        if start_date:
            self.from_calendar.setSelectedDate(start_date)
        from_layout.addWidget(self.from_calendar)
        calendar_layout.addWidget(from_group)
        
        to_group = QGroupBox("Дата окончания")
        to_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ff8c42;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ff8c42;
            }
        """)
        to_layout = QVBoxLayout(to_group)
        self.to_calendar = QCalendarWidget()
        self.to_calendar.setGridVisible(True)
        if end_date:
            self.to_calendar.setSelectedDate(end_date)
        to_layout.addWidget(self.to_calendar)
        calendar_layout.addWidget(to_group)
        
        layout.addLayout(calendar_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_dates(self):
        return self.from_calendar.selectedDate(), self.to_calendar.selectedDate()


class DateRangeWidget(QWidget):
    """Виджет для выбора диапазона дат с выпадающим списком и календарем"""
    
    periodChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self.init_ui()
        # Устанавливаем период "Последние 7 дней" и отправляем сигнал
        self.set_last_7_days(emit_signal=True)
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Период:"))
        
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            "Сегодня",
            "Вчера",
            "Последние 7 дней",
            "Последние 30 дней",
            "Этот месяц",
            "Прошлый месяц",
            "Всё время",
            "Выбрать даты..."
        ])
        self.period_combo.setMinimumWidth(150)
        self.period_combo.currentTextChanged.connect(self.on_period_changed)
        layout.addWidget(self.period_combo)
        
        self.range_label = QLabel("")
        self.range_label.setStyleSheet("color: #7f8c8d; padding: 5px; font-size: 12px;")
        self.range_label.setMinimumWidth(200)
        layout.addWidget(self.range_label)
        
        layout.addStretch()
    
    def on_period_changed(self, period_text):
        if self._updating:
            return
        
        self._updating = True
        
        try:
            if period_text == "Сегодня":
                self.set_today(emit_signal=False)
            elif period_text == "Вчера":
                self.set_yesterday(emit_signal=False)
            elif period_text == "Последние 7 дней":
                self.set_last_7_days(emit_signal=False)
            elif period_text == "Последние 30 дней":
                self.set_last_30_days(emit_signal=False)
            elif period_text == "Этот месяц":
                self.set_current_month(emit_signal=False)
            elif period_text == "Прошлый месяц":
                self.set_last_month(emit_signal=False)
            elif period_text == "Всё время":
                self.set_all_time(emit_signal=False)
            elif period_text == "Выбрать даты...":
                self.open_date_range_dialog()
                return
            
            self.periodChanged.emit()
        finally:
            self._updating = False
    
    def open_date_range_dialog(self):
        current_from = self.date_from if hasattr(self, 'date_from') else QDate.currentDate()
        current_to = self.date_to if hasattr(self, 'date_to') else QDate.currentDate()
        
        dialog = DateRangeDialog(self, current_from, current_to)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from_date, to_date = dialog.get_dates()
            self.date_from = from_date
            self.date_to = to_date
            self.update_range_label()
            self.periodChanged.emit()
    
    def update_range_label(self):
        if hasattr(self, 'date_from') and hasattr(self, 'date_to'):
            from_str = self.date_from.toString("yyyy-MM-dd")
            to_str = self.date_to.toString("yyyy-MM-dd")
            self.range_label.setText(f"{from_str} — {to_str}")
    
    def set_today(self, emit_signal=True):
        today = QDate.currentDate()
        self.date_from = today
        self.date_to = today
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Сегодня")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_yesterday(self, emit_signal=True):
        today = QDate.currentDate()
        yesterday = today.addDays(-1)
        self.date_from = yesterday
        self.date_to = yesterday
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Вчера")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_last_7_days(self, emit_signal=True):
        today = QDate.currentDate()
        week_ago = today.addDays(-7)
        self.date_from = week_ago
        self.date_to = today
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Последние 7 дней")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_last_30_days(self, emit_signal=True):
        today = QDate.currentDate()
        month_ago = today.addDays(-30)
        self.date_from = month_ago
        self.date_to = today
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Последние 30 дней")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_current_month(self, emit_signal=True):
        today = QDate.currentDate()
        first_day = QDate(today.year(), today.month(), 1)
        self.date_from = first_day
        self.date_to = today
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Этот месяц")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_last_month(self, emit_signal=True):
        today = QDate.currentDate()
        if today.month() == 1:
            last_month_date = QDate(today.year() - 1, 12, 1)
        else:
            last_month_date = QDate(today.year(), today.month() - 1, 1)
        last_day = last_month_date.addDays(last_month_date.daysInMonth() - 1)
        self.date_from = last_month_date
        self.date_to = last_day
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Прошлый месяц")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def set_all_time(self, emit_signal=True):
        today = QDate.currentDate()
        self.date_from = QDate(2024, 1, 1)
        self.date_to = today
        self.update_range_label()
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText("Всё время")
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def get_period(self):
        if hasattr(self, 'date_from') and hasattr(self, 'date_to'):
            return {
                'from': self.date_from.toString("yyyy-MM-dd"),
                'to': self.date_to.toString("yyyy-MM-dd")
            }
        # Если по какой-то причине даты не установлены, возвращаем последние 7 дней
        today = QDate.currentDate()
        week_ago = today.addDays(-7)
        return {
            'from': week_ago.toString("yyyy-MM-dd"),
            'to': today.toString("yyyy-MM-dd")
        }


class ComputerDetailsWindow(QMainWindow):
    """Окно с детальной информацией по компьютеру"""
    
    def __init__(self, hostname, computer_data):
        super().__init__()
        self.hostname = hostname
        self.computer_data = computer_data
        self.current_data = None
        self.computer_id = None
        self.current_disk_info = {'used_gb': None, 'total_gb': None}
        self.current_metrics = []
        self.event_statistics = {}
        self.all_events = []
        self.anomalies = []
        self.sessions = []
        
        self.init_ui()
        self.load_computer_info()
        self.connect_signals()
        
        # Принудительная загрузка данных после инициализации
        QTimer.singleShot(500, self.refresh_all_data)
    
    def init_ui(self):
        self.setWindowTitle(f"PC-RMDS | {self.computer_data.get('hostname', 'Unknown')}")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(get_main_window_stylesheet())
        self.setWindowIcon(get_app_icon())
        self.showMaximized()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff8c42, stop:1 #e67e22);
                border-radius: 12px;
                padding: 5px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        
        self.title_label = QLabel(self.computer_data.get('hostname', 'Unknown'))
        self.title_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.status_label)
        
        # Кнопка редактирования
        edit_btn = QPushButton("✎ Редактировать")
        edit_btn.setFixedWidth(120)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.3);
            }
        """)
        edit_btn.clicked.connect(self.edit_computer_info)
        header_layout.addWidget(edit_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        main_layout.addWidget(header_frame)
        
        # Выбор периода
        self.date_range = DateRangeWidget()
        main_layout.addWidget(self.date_range)
        
        # Табы
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #ff8c42;
                color: white;
            }
        """)
        
        self.tab_overview = QWidget()
        self.init_overview_tab()
        self.tabs.addTab(self.tab_overview, "Общая информация")
        
        self.tab_metrics = QWidget()
        self.init_metrics_tab()
        self.tabs.addTab(self.tab_metrics, "Метрики")
        
        self.tab_events = QWidget()
        self.init_events_tab()
        self.tabs.addTab(self.tab_events, "События")
        
        self.tab_sessions = QWidget()
        self.init_sessions_tab()
        self.tabs.addTab(self.tab_sessions, "Сессии")
        
        self.tab_anomalies = QWidget()
        self.init_anomalies_tab()
        self.tabs.addTab(self.tab_anomalies, "Аномалии")
        
        self.tab_reports = QWidget()
        self.init_reports_tab()
        self.tabs.addTab(self.tab_reports, "Отчеты")
        
        main_layout.addWidget(self.tabs)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        back_btn = QPushButton("Назад")
        back_btn.clicked.connect(self.go_back)
        back_btn.setMinimumWidth(120)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_layout.addWidget(back_btn)
        
        main_layout.addLayout(btn_layout)
    
    def connect_signals(self):
        self.date_range.periodChanged.connect(self.refresh_all_data)
    
    def edit_computer_info(self):
        """Открывает диалог редактирования информации о компьютере"""
        if not self.computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не определен")
            return
        
        dialog = EditComputerDialog(self.current_data, self.computer_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            update_data = dialog.get_update_data()
            if update_data:
                self.save_computer_info(update_data)
    
    def save_computer_info(self, update_data):
        """Сохраняет изменения информации о компьютере"""
        try:
            result = APIClient.update_computer(self.computer_id, update_data)
            if result:
                QMessageBox.information(self, "Успех", "Информация о компьютере обновлена")
                self.load_computer_info()
                self.refresh_all_data()
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось обновить информацию")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка при обновлении: {e}")
    
    def export_to_pdf(self):
        """Экспортирует отчет в PDF"""
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "Ошибка", "Библиотека ReportLab не установлена.\nУстановите: pip install reportlab")
            return
        
        try:
            # Выбираем файл для сохранения
            from PyQt6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить отчет", 
                f"report_{self.hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                "PDF files (*.pdf)"
            )
            
            if not file_path:
                return
            
            period = self.date_range.get_period()
            
            # Создаем PDF документ
            doc = SimpleDocTemplate(file_path, pagesize=A4, 
                                   rightMargin=72, leftMargin=72,
                                   topMargin=72, bottomMargin=72)
            
            story = []
            
            # Стили
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#ff8c42'),
                alignment=1  # Center
            )
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=10
            )
            normal_style = styles['Normal']
            
            # Заголовок
            title = Paragraph(f"Отчет по компьютеру: {self.hostname}", title_style)
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            # Период
            period_text = Paragraph(f"Период: {period['from']} — {period['to']}", normal_style)
            story.append(period_text)
            story.append(Spacer(1, 0.3*inch))
            
            # Информация о компьютере
            story.append(Paragraph("Информация о компьютере", heading_style))
            
            computer_info_data = [
                ["Характеристика", "Значение"],
                ["Hostname", self.current_data.get('hostname', '—')],
                ["IP адрес", self.current_data.get('current_ip', '—')],
                ["Пользователь", self.current_data.get('login', '—')],
                ["MAC адрес", self.current_data.get('mac_address', '—')],
                ["Тип", self.current_data.get('computer_type', '—')],
                ["ОС", f"{self.current_data.get('os_name', '—')} {self.current_data.get('os_version', '—')}"],
                ["CPU", self.current_data.get('cpu_model', '—')],
                ["RAM", f"{self.current_data.get('ram_total', '—')} GB"],
                ["Диск", f"{self.current_data.get('storage_total', '—')} GB"],
                ["GPU", self.current_data.get('gpu_model', '—')],
                ["Описание", self.current_data.get('description', '—')],
                ["Расположение", self.current_data.get('location', '—')],
                ["Отдел", self.current_data.get('department', '—')],
            ]
            
            computer_table = Table(computer_info_data, colWidths=[2*inch, 3*inch])
            computer_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff8c42')),
                ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(computer_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Средние метрики
            story.append(Paragraph("Средние показатели за период", heading_style))
            
            # Получаем средние метрики
            try:
                result = APIClient.get('/metrics/average', params={
                    'computer_id': self.computer_id,
                    'from': period['from'],
                    'to': period['to']
                })
                
                if result and result.get('success'):
                    avg_data = result.get('data', {}).get('average', {})
                    
                    metrics_data = [
                        ["Показатель", "Значение"],
                        ["CPU, %", f"{avg_data.get('cpu_usage', '—')}"],
                        ["RAM, %", f"{avg_data.get('ram_usage', '—')}"],
                        ["Disk, %", f"{avg_data.get('disk_usage', '—')}"],
                        ["Network отправлено, MB", f"{avg_data.get('network_sent_mb', '—')}"],
                        ["Network получено, MB", f"{avg_data.get('network_recv_mb', '—')}"],
                    ]
                    
                    metrics_table = Table(metrics_data, colWidths=[2*inch, 3*inch])
                    metrics_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff8c42')),
                        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (1, 0), 10),
                        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ]))
                    story.append(metrics_table)
                    story.append(Spacer(1, 0.3*inch))
            except Exception as e:
                print(f"Ошибка получения средних метрик для PDF: {e}")
            
            # События
            story.append(Paragraph("Статистика событий", heading_style))
            
            if self.event_statistics:
                events_data = [["Тип события", "Количество"]]
                for event_type, count in self.event_statistics.items():
                    events_data.append([event_type, str(count)])
                
                events_table = Table(events_data, colWidths=[2.5*inch, 2.5*inch])
                events_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff8c42')),
                    ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                    ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (1, 0), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                ]))
                story.append(events_table)
            else:
                story.append(Paragraph("Нет данных о событиях за выбранный период", normal_style))
            
            story.append(Spacer(1, 0.3*inch))
            
            # Аномалии
            story.append(Paragraph("Аномалии", heading_style))
            
            if self.anomalies:
                anomalies_data = [["Время", "CPU, %", "RAM, %", "Тип"]]
                for anomaly in self.anomalies[:50]:  # Ограничиваем 50 записями
                    cpu = anomaly.get('cpu_usage', '—')
                    ram = anomaly.get('ram_usage', '—')
                    anomaly_type = []
                    if cpu and isinstance(cpu, (int, float)) and cpu > 90:
                        anomaly_type.append("CPU")
                    if ram and isinstance(ram, (int, float)) and ram > 90:
                        anomaly_type.append("RAM")
                    anomalies_data.append([
                        anomaly.get('timestamp', '')[:19],
                        f"{cpu:.1f}" if cpu else "—",
                        f"{ram:.1f}" if ram else "—",
                        ", ".join(anomaly_type) if anomaly_type else "Высокая нагрузка"
                    ])
                
                anomalies_table = Table(anomalies_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1.5*inch])
                anomalies_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff8c42')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                ]))
                story.append(anomalies_table)
            else:
                story.append(Paragraph("Нет аномалий за выбранный период", normal_style))
            
            # Создаем PDF
            doc.build(story)
            
            QMessageBox.information(self, "Успех", f"Отчет сохранен в:\n{file_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка при создании PDF: {e}")
    
    def load_computer_info(self):
        try:
            result = APIClient.get('/computers', params={'search': self.hostname})
            if result and result.get('success'):
                computers_data = result.get('data', {})
                computers = computers_data.get('computers', [])
                for comp in computers:
                    if comp.get('hostname') == self.hostname:
                        self.computer_id = comp.get('computer_id')
                        break
            
            if self.computer_id:
                result = APIClient.get(f'/computers/{self.computer_id}')
                if result and result.get('success'):
                    self.current_data = result.get('data', {})
                else:
                    self.current_data = self.computer_data
            else:
                self.current_data = self.computer_data
            
            is_online = self.current_data.get('is_online', False)
            self.status_label.setText("В сети" if is_online else "Не в сети")
            
            self.update_computer_info_display()
            
        except Exception as e:
            print(f"Ошибка загрузки информации: {e}")
    
    def update_computer_info_display(self):
        if not hasattr(self, 'computer_info_text'):
            return
        
        data = self.current_data
        
        hostname = data.get('hostname', 'Unknown')
        ip_address = data.get('current_ip', self.computer_data.get('ip_address', 'Unknown'))
        user_login = data.get('login', self.computer_data.get('user_login', 'Не назначен'))
        full_name = data.get('full_name', '')
        mac_address = data.get('mac_address', 'Unknown')
        computer_type = data.get('computer_type', 'client')
        os_name = data.get('os_name', 'Unknown')
        os_version = data.get('os_version', '')
        os_architecture = data.get('os_architecture', '')
        cpu_model = data.get('cpu_model', 'Unknown')
        cpu_cores = data.get('cpu_cores', '?')
        ram_total = data.get('ram_total', '?')
        storage_total = data.get('storage_total', '?')
        gpu_model = data.get('gpu_model', 'Unknown')
        motherboard = data.get('motherboard', 'Unknown')
        bios_version = data.get('bios_version', 'Unknown')
        last_online = data.get('last_online', 'N/A')
        created_at = data.get('created_at', 'N/A')
        description = data.get('description', '—')
        location = data.get('location', '—')
        department = data.get('department', '—')
        inventory_number = data.get('inventory_number', '—')
        
        if last_online and isinstance(last_online, str):
            last_online = last_online[:19]
        if created_at and isinstance(created_at, str):
            created_at = created_at[:19]
        
        user_display = f"{user_login}" + (f" ({full_name})" if full_name else "")
        
        info_text = f"""
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 8px; width: 33%;"><b>Hostname:</b></td>
                <td style="padding: 8px;">{hostname}</td>
                <td style="padding: 8px; width: 33%;"><b>IP адрес:</b></td>
                <td style="padding: 8px;">{ip_address}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Пользователь:</b></td>
                <td style="padding: 8px;">{user_display}</td>
                <td style="padding: 8px;"><b>MAC адрес:</b></td>
                <td style="padding: 8px;">{mac_address}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Тип:</b></td>
                <td style="padding: 8px;">{computer_type}</td>
                <td style="padding: 8px;"><b>ОС:</b></td>
                <td style="padding: 8px;">{os_name} {os_version} {os_architecture}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>CPU:</b></td>
                <td style="padding: 8px;">{cpu_model} ({cpu_cores} ядер)</td>
                <td style="padding: 8px;"><b>RAM:</b></td>
                <td style="padding: 8px;">{ram_total} GB</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Диск:</b></td>
                <td style="padding: 8px;">{storage_total} GB</td>
                <td style="padding: 8px;"><b>GPU:</b></td>
                <td style="padding: 8px;">{gpu_model}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Материнская плата:</b></td>
                <td style="padding: 8px;">{motherboard}</td>
                <td style="padding: 8px;"><b>BIOS версия:</b></td>
                <td style="padding: 8px;">{bios_version}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Описание:</b></td>
                <td style="padding: 8px;" colspan="3">{description}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Расположение:</b></td>
                <td style="padding: 8px;">{location}</td>
                <td style="padding: 8px;"><b>Отдел:</b></td>
                <td style="padding: 8px;">{department}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Инв. номер:</b></td>
                <td style="padding: 8px;">{inventory_number}</td>
                <td style="padding: 8px;"><b>Создан:</b></td>
                <td style="padding: 8px;">{created_at}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><b>Последний вход:</b></td>
                <td style="padding: 8px;" colspan="3">{last_online}</td>
            </tr>
        </table>
        """
        self.computer_info_text.setText(info_text)
        
        if hasattr(self, 'disk_widget'):
            self.disk_widget.update_disk_info(
                self.current_disk_info.get('used_gb'),
                self.current_disk_info.get('total_gb')
            )
    
    def load_disk_space(self):
        """Загружает информацию о диске за выбранный период"""
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            # Получаем последнюю метрику за выбранный период
            result = APIClient.get('/metrics/performance', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'limit': 1
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                metrics = data.get('performance', [])
                if metrics:
                    last_metric = metrics[-1]
                    self.current_disk_info['used_gb'] = last_metric.get('disk_used_gb')
                    self.current_disk_info['total_gb'] = last_metric.get('disk_total_gb')
                    
                    if hasattr(self, 'disk_widget'):
                        self.disk_widget.update_disk_info(
                            self.current_disk_info['used_gb'],
                            self.current_disk_info['total_gb']
                        )
                        self.update_computer_info_display()
                    return
            
            # Если не удалось получить метрики, используем данные из computer_info
            total_gb = self.current_data.get('storage_total')
            if total_gb:
                self.current_disk_info['total_gb'] = float(total_gb)
                if hasattr(self, 'disk_widget'):
                    self.disk_widget.update_disk_info(
                        self.current_disk_info.get('used_gb'),
                        self.current_disk_info.get('total_gb')
                    )
                    
        except Exception as e:
            print(f"Ошибка загрузки информации о диске: {e}")
    
    def init_overview_tab(self):
        layout = QVBoxLayout(self.tab_overview)
        layout.setSpacing(15)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Информация о компьютере
        info_group = QGroupBox("Характеристики компьютера")
        info_group.setStyleSheet("""
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
        """)
        
        info_layout = QVBoxLayout(info_group)
        
        self.computer_info_text = QLabel()
        self.computer_info_text.setWordWrap(True)
        self.computer_info_text.setStyleSheet("padding: 10px; font-size: 13px;")
        info_layout.addWidget(self.computer_info_text)
        
        scroll_layout.addWidget(info_group)
        
        # Виджет свободного места на диске
        disk_group = QGroupBox("Состояние диска")
        disk_group.setStyleSheet("""
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
        """)
        
        disk_layout = QVBoxLayout(disk_group)
        self.disk_widget = DiskSpaceWidget()
        disk_layout.addWidget(self.disk_widget)
        
        scroll_layout.addWidget(disk_group)
        
        # Сводка за период
        summary_group = QGroupBox("Сводка за период")
        summary_group.setStyleSheet("""
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
        """)
        
        summary_layout = QGridLayout(summary_group)
        summary_layout.setSpacing(15)
        
        self.summary_cards = {}
        metrics = [
            ('cpu_avg', "Средний CPU", "—", "#3498db"),
            ('ram_avg', "Средняя RAM", "—", "#2ecc71"),
            ('disk_avg', "Средний Disk", "—", "#9b59b6"),
            ('network_total', "Сеть (MB)", "—", "#1abc9c"),
            ('events_total', "Всего событий", "—", "#e74c3c"),
            ('anomalies_total', "Аномалий", "—", "#f39c12"),
        ]
        
        row, col = 0, 0
        for key, title, value, color in metrics:
            card = self.create_summary_card(title, value, color)
            self.summary_cards[key] = card
            summary_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        scroll_layout.addWidget(summary_group)
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
    
    def create_summary_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 10px;
                border-left: 4px solid {color};
                padding: 10px;
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(5)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        
        card.value_label = value_label
        return card
    
    def init_metrics_tab(self):
        layout = QVBoxLayout(self.tab_metrics)
        
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(6)
        self.metrics_table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "RAM, GB", "Disk, %", "Network, MB/s"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.metrics_table)
    
    def init_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Тип события:"))
        
        self.event_type_filter = QComboBox()
        self.event_type_filter.addItems(["Все", "system_boot", "shutdown", "restart", "windows_event", "user_action", "windows_restart", "sleep"])
        self.event_type_filter.currentTextChanged.connect(self.filter_events)
        filter_layout.addWidget(self.event_type_filter)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(3)
        self.events_table.setHorizontalHeaderLabels(["Время", "Тип", "Описание"])
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.events_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.events_table)
        self.all_events = []
    
    def init_sessions_tab(self):
        layout = QVBoxLayout(self.tab_sessions)
        
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels(["ID", "Начало", "Конец", "Статус", "Длительность"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.cellDoubleClicked.connect(self.open_session_details)
        
        layout.addWidget(self.sessions_table)
    
    def init_anomalies_tab(self):
        layout = QVBoxLayout(self.tab_anomalies)
        
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Порог CPU:"))
        
        self.cpu_threshold = QComboBox()
        self.cpu_threshold.addItems(["80", "85", "90", "95"])
        self.cpu_threshold.setCurrentText("90")
        threshold_layout.addWidget(self.cpu_threshold)
        threshold_layout.addWidget(QLabel("%"))
        
        threshold_layout.addSpacing(20)
        threshold_layout.addWidget(QLabel("Порог RAM:"))
        
        self.ram_threshold = QComboBox()
        self.ram_threshold.addItems(["80", "85", "90", "95"])
        self.ram_threshold.setCurrentText("90")
        threshold_layout.addWidget(self.ram_threshold)
        threshold_layout.addWidget(QLabel("%"))
        
        self.refresh_anomalies_btn = QPushButton("Обновить")
        self.refresh_anomalies_btn.clicked.connect(self.load_anomalies)
        threshold_layout.addWidget(self.refresh_anomalies_btn)
        
        threshold_layout.addStretch()
        layout.addLayout(threshold_layout)
        
        self.anomalies_table = QTableWidget()
        self.anomalies_table.setColumnCount(4)
        self.anomalies_table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "Тип аномалии"])
        self.anomalies_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.anomalies_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.anomalies_table)
    
    def init_reports_tab(self):
        """Вкладка с отчетами"""
        layout = QVBoxLayout(self.tab_reports)
        
        # Панель управления
        control_panel = QFrame()
        control_panel.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 15px;
            }
        """)
        control_layout = QGridLayout(control_panel)
        control_layout.setSpacing(15)
        
        # Что показывать
        control_layout.addWidget(QLabel("Тип данных:"), 0, 0)
        self.report_data_type = QComboBox()
        self.report_data_type.addItems(["Метрики", "События", "Аномалии"])
        self.report_data_type.setMinimumWidth(150)
        self.report_data_type.currentTextChanged.connect(self.on_report_data_type_changed)
        control_layout.addWidget(self.report_data_type, 0, 1)
        
        # Для метрик - выбор показателя
        control_layout.addWidget(QLabel("Показатель:"), 0, 2)
        self.report_metric = QComboBox()
        self.report_metric.addItems(["Все метрики", "CPU, %", "RAM, %", "Disk, %", "Network, MB/s"])
        self.report_metric.setMinimumWidth(120)
        control_layout.addWidget(self.report_metric, 0, 3)
        
        # Вид отображения
        control_layout.addWidget(QLabel("Вид:"), 1, 0)
        self.report_view_type = QComboBox()
        self.report_view_type.addItems(["Таблица", "Гистограмма", "Линейный график", "Круговая диаграмма"])
        self.report_view_type.setMinimumWidth(150)
        self.report_view_type.currentTextChanged.connect(self.on_report_view_type_changed)
        control_layout.addWidget(self.report_view_type, 1, 1)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("Сформировать отчет")
        self.generate_btn.setMinimumHeight(35)
        self.generate_btn.setMinimumWidth(150)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff8c42;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.generate_btn.clicked.connect(self.generate_report)
        button_layout.addWidget(self.generate_btn)
        
        # Кнопка экспорта в PDF
        self.export_pdf_btn = QPushButton("📄 Экспорт в PDF")
        self.export_pdf_btn.setMinimumHeight(35)
        self.export_pdf_btn.setMinimumWidth(150)
        self.export_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        self.export_pdf_btn.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(self.export_pdf_btn)
        
        control_layout.addLayout(button_layout, 1, 2, 1, 2)
        
        # Настройка видимости
        self.on_report_data_type_changed(self.report_data_type.currentText())
        
        layout.addWidget(control_panel)
        
        # Область для отчета
        self.report_area = QScrollArea()
        self.report_area.setWidgetResizable(True)
        self.report_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                background-color: white;
            }
        """)
        
        self.report_container = QWidget()
        self.report_container_layout = QVBoxLayout(self.report_container)
        self.report_area.setWidget(self.report_container)
        
        layout.addWidget(self.report_area)
    
    def open_session_details(self, row, column):
        """Открывает диалог с деталями сессии"""
        if not self.sessions or row >= len(self.sessions):
            return
        
        session = self.sessions[row]
        dialog = EditSessionDialog(session, self)
        dialog.exec()
    
    def on_report_data_type_changed(self, data_type):
        """Обработчик изменения типа данных"""
        self.report_metric.setVisible(data_type == "Метрики")
        
        if data_type == "События":
            current_view = self.report_view_type.currentText()
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Круговая диаграмма"])
            if current_view not in ["Таблица", "Круговая диаграмма"]:
                self.report_view_type.setCurrentText("Таблица")
        elif data_type == "Аномалии":
            current_view = self.report_view_type.currentText()
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Гистограмма"])
            if current_view not in ["Таблица", "Гистограмма"]:
                self.report_view_type.setCurrentText("Таблица")
        else:  # Метрики
            current_view = self.report_view_type.currentText()
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Гистограмма", "Линейный график"])
            if current_view not in ["Таблица", "Гистограмма", "Линейный график"]:
                self.report_view_type.setCurrentText("Таблица")
    
    def on_report_view_type_changed(self, view_type):
        pass
    
    def refresh_all_data(self):
        """Обновляет все данные"""
        if not self.computer_id:
            self.load_computer_info()
            if not self.computer_id:
                return
        
        self.load_overview_summary()
        self.load_metrics()
        self.load_events()
        self.load_sessions()
        self.load_anomalies()
        self.load_disk_space()
    
    def load_overview_summary(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/average', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                avg_data = data.get('average', {})
                
                cpu = avg_data.get('cpu_usage')
                ram = avg_data.get('ram_usage')
                disk = avg_data.get('disk_usage')
                network_sent = avg_data.get('network_sent_mb', 0)
                network_recv = avg_data.get('network_recv_mb', 0)
                network_total = network_sent + network_recv
                
                self.summary_cards['cpu_avg'].value_label.setText(f"{cpu:.1f}%" if cpu else "—")
                self.summary_cards['ram_avg'].value_label.setText(f"{ram:.1f}%" if ram else "—")
                self.summary_cards['disk_avg'].value_label.setText(f"{disk:.1f}%" if disk else "—")
                self.summary_cards['network_total'].value_label.setText(f"{network_total:.0f}" if network_total else "—")
        except Exception as e:
            print(f"Ошибка загрузки средних метрик: {e}")
        
        try:
            result = APIClient.get('/metrics/events/statistics', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                total_events = data.get('total_events', 0)
                self.summary_cards['events_total'].value_label.setText(str(total_events))
        except Exception as e:
            print(f"Ошибка загрузки статистики событий: {e}")
        
        try:
            result = APIClient.get('/metrics/anomalies', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'cpu_threshold': 0,
                'ram_threshold': 0
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                anomalies_count = data.get('count', 0)
                self.summary_cards['anomalies_total'].value_label.setText(str(anomalies_count))
        except Exception as e:
            print(f"Ошибка загрузки общего количества аномалий: {e}")
    
    def load_metrics(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/performance', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                self.current_metrics = data.get('performance', [])
                
                self.metrics_table.setRowCount(len(self.current_metrics))
                
                for row, metric in enumerate(self.current_metrics):
                    timestamp = metric.get('timestamp', '')[:19]
                    cpu = metric.get('cpu_usage')
                    ram_percent = metric.get('ram_usage')
                    ram_gb = metric.get('ram_used_gb')
                    disk = metric.get('disk_usage')
                    network = metric.get('network_sent_mb', 0) + metric.get('network_recv_mb', 0)
                    
                    self.metrics_table.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.metrics_table.setItem(row, 1, QTableWidgetItem(f"{cpu:.1f}" if cpu else "—"))
                    self.metrics_table.setItem(row, 2, QTableWidgetItem(f"{ram_percent:.1f}" if ram_percent else "—"))
                    self.metrics_table.setItem(row, 3, QTableWidgetItem(f"{ram_gb:.1f}" if ram_gb else "—"))
                    self.metrics_table.setItem(row, 4, QTableWidgetItem(f"{disk:.1f}" if disk else "—"))
                    self.metrics_table.setItem(row, 5, QTableWidgetItem(f"{network:.2f}" if network else "—"))
            else:
                self.current_metrics = []
                self.metrics_table.setRowCount(0)
                
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
            self.current_metrics = []
            self.metrics_table.setRowCount(0)
    
    def load_events(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        try:
            result = APIClient.get('/metrics/events/statistics', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                self.event_statistics = data.get('statistics', {})
                
                events_result = APIClient.get('/metrics/events', params={
                    'computer_id': self.computer_id,
                    'from': period['from'],
                    'to': period['to']
                })
                if events_result and events_result.get('success'):
                    events_data = events_result.get('data', {})
                    self.all_events = events_data.get('events', [])
                    self.filter_events()
            else:
                self.event_statistics = {}
                self.all_events = []
                self.events_table.setRowCount(0)
                
        except Exception as e:
            print(f"Ошибка загрузки событий: {e}")
            self.event_statistics = {}
            self.all_events = []
            self.events_table.setRowCount(0)
    
    def filter_events(self):
        filter_type = self.event_type_filter.currentText()
        
        filtered = self.all_events
        if filter_type != "Все":
            filtered = [e for e in self.all_events if e.get('type') == filter_type or 
                       e.get('data', {}).get('action_type') == filter_type]
        
        self.events_table.setRowCount(len(filtered))
        
        for row, event in enumerate(filtered):
            timestamp = event.get('timestamp', '')[:19]
            event_type = event.get('type', event.get('data', {}).get('action_type', 'unknown'))
            description = self.get_event_description(event)
            
            self.events_table.setItem(row, 0, QTableWidgetItem(timestamp))
            self.events_table.setItem(row, 1, QTableWidgetItem(event_type))
            self.events_table.setItem(row, 2, QTableWidgetItem(description))
    
    def get_event_description(self, event):
        event_type = event.get('type', '')
        data = event.get('data', {})
        
        descriptions = {
            'user_action': data.get('description', f"Действие: {data.get('action_type', 'unknown')}"),
            'windows_event': data.get('message', f"Событие Windows: {data.get('event_id', 'unknown')}"),
            'windows_event_grouped': f"Группа событий: {len(data.get('events', []))} событий",
            'system_boot': "Загрузка системы",
            'shutdown': "Выключение системы",
            'restart': "Перезагрузка системы",
            'windows_restart': "Перезагрузка Windows",
            'sleep': "Спящий режим",
        }
        
        return descriptions.get(event_type, f"Событие: {event_type}")
    
    def parse_datetime(self, dt_str):
        if not dt_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(dt_str)
            return dt.replace(tzinfo=None)
        except:
            try:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                return dt.replace(tzinfo=None)
            except:
                try:
                    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
                except:
                    try:
                        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    except:
                        return None
    
    def load_sessions(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        from_date = datetime.strptime(period['from'], "%Y-%m-%d")
        to_date = datetime.strptime(period['to'], "%Y-%m-%d")
        to_date = to_date.replace(hour=23, minute=59, second=59)
        
        try:
            result = APIClient.get(f'/computers/{self.computer_id}/sessions')
            
            sessions = []
            if result and result.get('success'):
                data = result.get('data', {})
                self.sessions = data.get('sessions', [])
                sessions = self.sessions
            
            if sessions:
                filtered_sessions = []
                for session in sessions:
                    start_time_str = session.get('start_time', '')
                    start_time = self.parse_datetime(start_time_str)
                    
                    if start_time:
                        if from_date <= start_time <= to_date:
                            filtered_sessions.append(session)
                
                self.sessions_table.setRowCount(len(filtered_sessions))
                
                for row, session in enumerate(filtered_sessions):
                    session_id = session.get('session_id', '—')
                    start_time_str = session.get('start_time', '')
                    start_time = self.parse_datetime(start_time_str)
                    start_display = start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else str(start_time_str)[:19] if start_time_str else "—"
                    
                    end_time_str = session.get('end_time')
                    status = session.get('status_name', 'active')
                    status_display = "Активна" if status == 'active' else "Завершена"
                    
                    if end_time_str:
                        end_time = self.parse_datetime(end_time_str)
                        end_display = end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else str(end_time_str)[:19]
                    else:
                        end_display = "Активна"
                        end_time = None
                    
                    duration = ""
                    if start_time:
                        end = end_time if end_time else datetime.now()
                        delta = end - start_time
                        hours = int(delta.total_seconds() // 3600)
                        minutes = int((delta.total_seconds() % 3600) // 60)
                        seconds = int(delta.total_seconds() % 60)
                        
                        if hours > 0:
                            duration = f"{hours}ч {minutes}м"
                        elif minutes > 0:
                            duration = f"{minutes}м {seconds}с"
                        else:
                            duration = f"{seconds}с"
                    
                    self.sessions_table.setItem(row, 0, QTableWidgetItem(str(session_id)))
                    self.sessions_table.setItem(row, 1, QTableWidgetItem(start_display))
                    self.sessions_table.setItem(row, 2, QTableWidgetItem(end_display))
                    self.sessions_table.setItem(row, 3, QTableWidgetItem(status_display))
                    self.sessions_table.setItem(row, 4, QTableWidgetItem(duration))
                
                self.statusBar().showMessage(f"Загружено {len(filtered_sessions)} сессий за период", 3000)
            else:
                self.sessions_table.setRowCount(0)
                self.statusBar().showMessage("Нет сессий за выбранный период", 3000)
                
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
            self.sessions_table.setRowCount(0)
    
    def load_anomalies(self):
        if not self.computer_id:
            return
        
        period = self.date_range.get_period()
        
        cpu_thresh = int(self.cpu_threshold.currentText())
        ram_thresh = int(self.ram_threshold.currentText())
        
        try:
            result = APIClient.get('/metrics/anomalies', params={
                'computer_id': self.computer_id,
                'from': period['from'],
                'to': period['to'],
                'cpu_threshold': cpu_thresh,
                'ram_threshold': ram_thresh
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                self.anomalies = data.get('anomalies', [])
                
                self.anomalies_table.setRowCount(len(self.anomalies))
                
                for row, anomaly in enumerate(self.anomalies):
                    timestamp = anomaly.get('timestamp', '')[:19]
                    cpu = anomaly.get('cpu_usage')
                    ram = anomaly.get('ram_usage')
                    
                    anomaly_type = []
                    if cpu and isinstance(cpu, (int, float)) and cpu > cpu_thresh:
                        anomaly_type.append(f"CPU > {cpu_thresh}%")
                    if ram and isinstance(ram, (int, float)) and ram > ram_thresh:
                        anomaly_type.append(f"RAM > {ram_thresh}%")
                    
                    self.anomalies_table.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.anomalies_table.setItem(row, 1, QTableWidgetItem(f"{cpu:.1f}" if cpu else "—"))
                    self.anomalies_table.setItem(row, 2, QTableWidgetItem(f"{ram:.1f}" if ram else "—"))
                    self.anomalies_table.setItem(row, 3, QTableWidgetItem(", ".join(anomaly_type) if anomaly_type else "Высокая нагрузка"))
            else:
                self.anomalies = []
                self.anomalies_table.setRowCount(0)
                
        except Exception as e:
            print(f"Ошибка загрузки аномалий: {e}")
            self.anomalies = []
            self.anomalies_table.setRowCount(0)
    
    def generate_report(self):
        """Генерирует отчет на основе выбранных параметров"""
        data_type = self.report_data_type.currentText()
        view_type = self.report_view_type.currentText()
        period = self.date_range.get_period()
        
        self.clear_report_area()
        
        title = QLabel(f"Отчет: {data_type}\nПериод: {period['from']} — {period['to']}")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #ff8c42;
            padding: 10px;
            border-bottom: 2px solid #ff8c42;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(title)
        
        if data_type == "Метрики":
            self.generate_metrics_report_view(view_type, period)
        elif data_type == "События":
            self.generate_events_report_view(view_type, period)
        elif data_type == "Аномалии":
            self.generate_anomalies_report_view(view_type, period)
    
    def clear_report_area(self):
        while self.report_container_layout.count():
            child = self.report_container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def generate_metrics_report_view(self, view_type, period):
        if not self.current_metrics:
            error_label = QLabel("Нет данных метрик за выбранный период")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.report_container_layout.addWidget(error_label)
            return
        
        selected_metric = self.report_metric.currentText()
        
        if view_type == "Таблица":
            if selected_metric == "Все метрики":
                self.create_metrics_full_table(period)
            else:
                metric_map = {
                    "CPU, %": ("cpu_usage", "CPU, %"),
                    "RAM, %": ("ram_usage", "RAM, %"),
                    "Disk, %": ("disk_usage", "Disk, %"),
                    "Network, MB/s": ("network", "Network, MB/s")
                }
                metric_key, metric_name = metric_map.get(selected_metric, ("cpu_usage", "CPU, %"))
                self.create_metrics_single_table(metric_key, metric_name, period)
        elif view_type == "Гистограмма":
            if selected_metric == "Все метрики":
                self.create_metrics_all_histograms(period)
            else:
                metric_map = {
                    "CPU, %": ("cpu_usage", "CPU, %"),
                    "RAM, %": ("ram_usage", "RAM, %"),
                    "Disk, %": ("disk_usage", "Disk, %"),
                    "Network, MB/s": ("network", "Network, MB/s")
                }
                metric_key, metric_name = metric_map.get(selected_metric, ("cpu_usage", "CPU, %"))
                self.create_metrics_single_histogram(metric_key, metric_name, period)
        elif view_type == "Линейный график":
            if selected_metric == "Все метрики":
                self.create_metrics_all_line_charts(period)
            else:
                metric_map = {
                    "CPU, %": ("cpu_usage", "CPU, %"),
                    "RAM, %": ("ram_usage", "RAM, %"),
                    "Disk, %": ("disk_usage", "Disk, %"),
                    "Network, MB/s": ("network", "Network, MB/s")
                }
                metric_key, metric_name = metric_map.get(selected_metric, ("cpu_usage", "CPU, %"))
                self.create_metrics_single_line_chart(metric_key, metric_name, period)
    
    def create_metrics_full_table(self, period):
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "RAM, GB", "Disk, %", "Network, MB/s"])
        table.setRowCount(len(self.current_metrics))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, metric in enumerate(self.current_metrics):
            timestamp = metric.get('timestamp', '')[:19]
            cpu = metric.get('cpu_usage')
            ram_percent = metric.get('ram_usage')
            ram_gb = metric.get('ram_used_gb')
            disk = metric.get('disk_usage')
            network = metric.get('network_sent_mb', 0) + metric.get('network_recv_mb', 0)
            
            table.setItem(row, 0, QTableWidgetItem(timestamp))
            table.setItem(row, 1, QTableWidgetItem(f"{cpu:.1f}" if cpu else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{ram_percent:.1f}" if ram_percent else "—"))
            table.setItem(row, 3, QTableWidgetItem(f"{ram_gb:.1f}" if ram_gb else "—"))
            table.setItem(row, 4, QTableWidgetItem(f"{disk:.1f}" if disk else "—"))
            table.setItem(row, 5, QTableWidgetItem(f"{network:.2f}" if network else "—"))
        
        self.report_container_layout.addWidget(table)
    
    def create_metrics_single_table(self, metric_key, metric_name, period):
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Время", metric_name])
        table.setRowCount(len(self.current_metrics))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, metric in enumerate(self.current_metrics):
            timestamp = metric.get('timestamp', '')[:19]
            
            if metric_key == "network":
                value = metric.get('network_sent_mb', 0) + metric.get('network_recv_mb', 0)
                value_str = f"{value:.2f}"
            else:
                value = metric.get(metric_key, 0)
                value_str = f"{value:.1f}" if value else "—"
            
            table.setItem(row, 0, QTableWidgetItem(timestamp))
            table.setItem(row, 1, QTableWidgetItem(value_str))
        
        self.report_container_layout.addWidget(table)
    
    def create_metrics_single_histogram(self, metric_key, metric_name, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        daily_data = {}
        for m in self.current_metrics:
            date_str = m.get('timestamp', '')[:10]
            
            if metric_key == "network":
                value = m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0)
            else:
                value = m.get(metric_key, 0)
            
            if date_str not in daily_data:
                daily_data[date_str] = []
            daily_data[date_str].append(value)
        
        chart_data = []
        for date_str, values in daily_data.items():
            avg_value = sum(values) / len(values)
            chart_data.append({
                'category': date_str,
                'value': avg_value
            })
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        categories = [d['category'] for d in chart_data]
        values = [d['value'] for d in chart_data]
        
        bars = ax.bar(categories, values, color='#ff8c42', edgecolor='white', linewidth=2)
        ax.set_title(f"Средний {metric_name} по дням\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        ax.set_xlabel("Дата", fontsize=10, color='#7f8c8d')
        ax.set_ylabel(metric_name, fontsize=10, color='#7f8c8d')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_facecolor('#f8f9fa')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.annotate(f'{value:.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha='center', va='bottom', fontsize=8)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def create_metrics_all_histograms(self, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        cpu_values = [m.get('cpu_usage', 0) for m in self.current_metrics if m.get('cpu_usage') is not None]
        ram_values = [m.get('ram_usage', 0) for m in self.current_metrics if m.get('ram_usage') is not None]
        disk_values = [m.get('disk_usage', 0) for m in self.current_metrics if m.get('disk_usage') is not None]
        network_values = [m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0) 
                         for m in self.current_metrics if m.get('network_sent_mb') is not None]
        
        cpu_avg = sum(cpu_values) / len(cpu_values) if cpu_values else 0
        ram_avg = sum(ram_values) / len(ram_values) if ram_values else 0
        disk_avg = sum(disk_values) / len(disk_values) if disk_values else 0
        network_avg = sum(network_values) / len(network_values) if network_values else 0
        
        categories = ['CPU, %', 'RAM, %', 'Disk, %', 'Network, MB/s']
        values = [cpu_avg, ram_avg, disk_avg, network_avg]
        colors = ['#3498db', '#2ecc71', '#9b59b6', '#e74c3c']
        
        figure = Figure(figsize=(10, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        bars = ax.bar(categories, values, color=colors, edgecolor='white', linewidth=2)
        ax.set_title(f"Средние значения метрик\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        ax.set_ylabel("Среднее значение", fontsize=11, color='#7f8c8d')
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_facecolor('#f8f9fa')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.annotate(f'{value:.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 5),
                       textcoords="offset points",
                       ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def create_metrics_single_line_chart(self, metric_key, metric_name, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        chart_data = []
        for m in self.current_metrics:
            timestamp = m.get('timestamp', '')
            
            if metric_key == "network":
                value = m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0)
            else:
                value = m.get(metric_key, 0)
            
            chart_data.append({
                'timestamp': timestamp,
                'value': value
            })
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        timestamps = [d['timestamp'][:16] for d in chart_data]
        values = [d['value'] for d in chart_data]
        
        ax.plot(timestamps, values, color='#ff8c42', linewidth=2, marker='o', markersize=3)
        ax.set_title(f"Динамика {metric_name}\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        ax.set_xlabel("Время", fontsize=10, color='#7f8c8d')
        ax.set_ylabel(metric_name, fontsize=10, color='#7f8c8d')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        ax.set_facecolor('#f8f9fa')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def create_metrics_all_line_charts(self, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        timestamps = [m.get('timestamp', '')[:16] for m in self.current_metrics]
        cpu_vals = [m.get('cpu_usage', 0) for m in self.current_metrics]
        ram_vals = [m.get('ram_usage', 0) for m in self.current_metrics]
        disk_vals = [m.get('disk_usage', 0) for m in self.current_metrics]
        network_vals = [m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0) for m in self.current_metrics]
        
        figure = Figure(figsize=(12, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        ax.plot(timestamps, cpu_vals, color='#3498db', linewidth=2, marker='o', markersize=3, label='CPU, %')
        ax.plot(timestamps, ram_vals, color='#2ecc71', linewidth=2, marker='s', markersize=3, label='RAM, %')
        ax.plot(timestamps, disk_vals, color='#9b59b6', linewidth=2, marker='^', markersize=3, label='Disk, %')
        
        ax2 = ax.twinx()
        ax2.plot(timestamps, network_vals, color='#e74c3c', linewidth=2, marker='d', markersize=3, label='Network, MB/s')
        ax2.set_ylabel('Network, MB/s', fontsize=10, color='#e74c3c')
        ax2.tick_params(axis='y', labelcolor='#e74c3c')
        
        ax.set_title(f"Динамика метрик\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        ax.set_xlabel("Время", fontsize=10, color='#7f8c8d')
        ax.set_ylabel("CPU / RAM / Disk, %", fontsize=10, color='#2c3e50')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        ax.set_facecolor('#f8f9fa')
        
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def generate_events_report_view(self, view_type, period):
        if not self.event_statistics:
            error_label = QLabel("Нет данных событий за выбранный период")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.report_container_layout.addWidget(error_label)
            return
        
        if view_type == "Таблица":
            self.create_events_table(period)
        elif view_type == "Круговая диаграмма":
            self.create_events_pie_chart(period)
    
    def create_events_table(self, period):
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Тип события", "Количество"])
        table.setRowCount(len(self.event_statistics))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, (event_type, count) in enumerate(self.event_statistics.items()):
            table.setItem(row, 0, QTableWidgetItem(event_type))
            table.setItem(row, 1, QTableWidgetItem(str(count)))
        
        self.report_container_layout.addWidget(table)
    
    def create_events_pie_chart(self, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        figure = Figure(figsize=(8, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        categories = list(self.event_statistics.keys())
        values = list(self.event_statistics.values())
        
        colors = ['#ff8c42', '#2ecc71', '#3498db', '#9b59b6', '#e74c3c', '#1abc9c', '#f39c12', '#e67e22']
        
        wedges, texts, autotexts = ax.pie(values, labels=categories, autopct='%1.1f%%',
                                          colors=colors[:len(categories)],
                                          startangle=90)
        
        ax.set_title(f"Распределение событий по типам\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        
        for text in texts:
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def generate_anomalies_report_view(self, view_type, period):
        if not self.anomalies:
            error_label = QLabel("Нет данных аномалий за выбранный период")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.report_container_layout.addWidget(error_label)
            return
        
        if view_type == "Таблица":
            self.create_anomalies_table(period)
        elif view_type == "Гистограмма":
            self.create_anomalies_histogram(period)
    
    def create_anomalies_table(self, period):
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "Тип"])
        table.setRowCount(len(self.anomalies))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        cpu_thresh = int(self.cpu_threshold.currentText())
        ram_thresh = int(self.ram_threshold.currentText())
        
        for row, anomaly in enumerate(self.anomalies):
            timestamp = anomaly.get('timestamp', '')[:19]
            cpu = anomaly.get('cpu_usage')
            ram = anomaly.get('ram_usage')
            
            anomaly_type = []
            if cpu and isinstance(cpu, (int, float)) and cpu > cpu_thresh:
                anomaly_type.append("CPU")
            if ram and isinstance(ram, (int, float)) and ram > ram_thresh:
                anomaly_type.append("RAM")
            
            table.setItem(row, 0, QTableWidgetItem(timestamp))
            table.setItem(row, 1, QTableWidgetItem(f"{cpu:.1f}" if cpu else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{ram:.1f}" if ram else "—"))
            table.setItem(row, 3, QTableWidgetItem(", ".join(anomaly_type) if anomaly_type else "Высокая нагрузка"))
        
        self.report_container_layout.addWidget(table)
    
    def create_anomalies_histogram(self, period):
        if not MATPLOTLIB_AVAILABLE:
            self.show_matplotlib_error()
            return
        
        daily_anomalies = {}
        for anomaly in self.anomalies:
            date_str = anomaly.get('timestamp', '')[:10]
            if date_str not in daily_anomalies:
                daily_anomalies[date_str] = 0
            daily_anomalies[date_str] += 1
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        categories = list(daily_anomalies.keys())
        values = list(daily_anomalies.values())
        
        bars = ax.bar(categories, values, color='#e74c3c', edgecolor='white', linewidth=2)
        ax.set_title(f"Количество аномалий по дням\n{period['from']} — {period['to']}", 
                     fontsize=14, fontweight='bold', color='#2c3e50')
        ax.set_xlabel("Дата", fontsize=10, color='#7f8c8d')
        ax.set_ylabel("Количество аномалий", fontsize=10, color='#7f8c8d')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_facecolor('#f8f9fa')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.annotate(str(value),
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha='center', va='bottom', fontsize=8)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def show_matplotlib_error(self):
        error_label = QLabel(
            "Для отображения графиков установите matplotlib:\n"
            "pip install matplotlib\n\n"
            "Или используйте табличный вид отчета"
        )
        error_label.setStyleSheet("color: orange; padding: 20px; background-color: #f8f9fa; border-radius: 8px;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(error_label)
    
    def go_back(self):
        from .admin_panel import AdminPanelWindow
        self.admin_panel = AdminPanelWindow({'login': self.computer_data.get('user_login', 'Admin')})
        self.admin_panel.show()
        self.close()
    
    def closeEvent(self, event):
        from .admin_panel import AdminPanelWindow
        self.admin_panel = AdminPanelWindow({'login': self.computer_data.get('user_login', 'Admin')})
        self.admin_panel.show()
        event.accept()