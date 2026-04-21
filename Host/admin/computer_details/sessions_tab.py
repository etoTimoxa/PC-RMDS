# ui/computer_details/sessions_tab.py

from datetime import datetime
from email.utils import parsedate_to_datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt


class SessionsTab(QWidget):
    """Вкладка с сессиями"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.sessions = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels(["ID", "Начало", "Конец", "Статус", "Длительность"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.cellDoubleClicked.connect(self.open_session_details)
        
        layout.addWidget(self.sessions_table)
    
    def update_sessions(self, sessions):
        """Обновляет таблицу сессий"""
        self.sessions = sessions
        self.sessions_table.setRowCount(len(sessions))
        
        for row, session in enumerate(sessions):
            session_id = session.get('session_id', '—')
            start_time = session.get('start_time', '')
            end_time = session.get('end_time')
            status = session.get('status_name', 'active')
            
            # Преобразуем RFC дату в читаемый формат
            start_display = self._format_rfc_date(start_time)
            end_display = self._format_rfc_date(end_time) if end_time else "Активна"
            status_display = "Активна" if status == 'active' else "Завершена"
            
            # Вычисляем длительность
            duration = self._calculate_duration(start_time, end_time)
            
            self.sessions_table.setItem(row, 0, QTableWidgetItem(str(session_id)))
            self.sessions_table.setItem(row, 1, QTableWidgetItem(start_display))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(end_display))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(status_display))
            self.sessions_table.setItem(row, 4, QTableWidgetItem(duration))
    
    def _format_rfc_date(self, rfc_date):
        """Преобразует RFC 2822 дату в YYYY-MM-DD HH:MM:SS"""
        if not rfc_date:
            return "—"
        try:
            dt = parsedate_to_datetime(rfc_date)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return str(rfc_date)[:19] if rfc_date else "—"
    
    def _calculate_duration(self, start_time, end_time=None):
        """Вычисляет длительность сессии"""
        try:
            if not start_time:
                return "—"
            
            start = parsedate_to_datetime(start_time)
            
            if end_time:
                end = parsedate_to_datetime(end_time)
            else:
                end = datetime.now()
            
            delta = end - start
            total_seconds = int(delta.total_seconds())
            
            if total_seconds < 0:
                return "—"
            
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if days > 0:
                return f"{days}д {hours}ч"
            elif hours > 0:
                return f"{hours}ч {minutes}м"
            elif minutes > 0:
                return f"{minutes}м {seconds}с"
            else:
                return f"{seconds}с"
                
        except Exception as e:
            print(f"Ошибка расчета длительности: {e}")
            return "—"
    
    def open_session_details(self, row, column):
        if not self.sessions or row >= len(self.sessions):
            return
        
        from .dialogs import EditSessionDialog
        session = self.sessions[row]
        dialog = EditSessionDialog(session, self.parent_window.computer_id if self.parent_window else None, self)
        dialog.exec()
    
    def get_sessions(self):
        return self.sessions