"""Вспомогательные виджеты"""

from qtpy.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QComboBox, QFrame, QDialog
from qtpy.QtCore import QDate
from qtpy.QtCore import Signal as Signal
from qtpy.QtGui import QColor, QIcon, QPixmap
from pathlib import Path


def get_app_icon() -> QIcon:
    """Возвращает иконку приложения"""
    icon_path = Path(__file__).parent.parent.parent / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    icon_path = Path(__file__).parent.parent.parent / "app_icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    icon_path = Path.cwd() / "app_icon.png"
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
            
            self.progress_bar.setValue(int(used_percent))
            self.progress_bar.setFormat(f"Занято: {used_percent:.1f}%")
            
            self.info_label.setText(f"Свободно: {free_gb:.1f} GB из {total_gb:.1f} GB")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Нет данных")
            self.info_label.setText("Нет данных о диске")


class DateRangeWidget(QWidget):
    """Виджет для выбора диапазона дат"""
    
    periodChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self.init_ui()
        self.set_last_7_days(emit_signal=True)
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Период:"))
        
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            "Сегодня", "Вчера", "Последние 7 дней", "Последние 30 дней",
            "Этот месяц", "Прошлый месяц", "Всё время", "Выбрать даты..."
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
        from .dialogs import DateRangeDialog
        current_from = getattr(self, 'date_from', QDate.currentDate())
        current_to = getattr(self, 'date_to', QDate.currentDate())
        
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
        self._set_combo_text("Сегодня", emit_signal)
    
    def set_yesterday(self, emit_signal=True):
        today = QDate.currentDate()
        yesterday = today.addDays(-1)
        self.date_from = yesterday
        self.date_to = yesterday
        self.update_range_label()
        self._set_combo_text("Вчера", emit_signal)
    
    def set_last_7_days(self, emit_signal=True):
        today = QDate.currentDate()
        week_ago = today.addDays(-7)
        self.date_from = week_ago
        self.date_to = today
        self.update_range_label()
        self._set_combo_text("Последние 7 дней", emit_signal)
    
    def set_last_30_days(self, emit_signal=True):
        today = QDate.currentDate()
        month_ago = today.addDays(-30)
        self.date_from = month_ago
        self.date_to = today
        self.update_range_label()
        self._set_combo_text("Последние 30 дней", emit_signal)
    
    def set_current_month(self, emit_signal=True):
        today = QDate.currentDate()
        first_day = QDate(today.year(), today.month(), 1)
        self.date_from = first_day
        self.date_to = today
        self.update_range_label()
        self._set_combo_text("Этот месяц", emit_signal)
    
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
        self._set_combo_text("Прошлый месяц", emit_signal)
    
    def set_all_time(self, emit_signal=True):
        today = QDate.currentDate()
        self.date_from = QDate(2024, 1, 1)
        self.date_to = today
        self.update_range_label()
        self._set_combo_text("Всё время", emit_signal)
    
    def _set_combo_text(self, text, emit_signal):
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentText(text)
        self.period_combo.blockSignals(False)
        if emit_signal:
            self.periodChanged.emit()
    
    def get_period(self):
        if hasattr(self, 'date_from') and hasattr(self, 'date_to'):
            return {
                'from': self.date_from.toString("yyyy-MM-dd"),
                'to': self.date_to.toString("yyyy-MM-dd")
            }
        today = QDate.currentDate()
        week_ago = today.addDays(-7)
        return {
            'from': week_ago.toString("yyyy-MM-dd"),
            'to': today.toString("yyyy-MM-dd")
        }