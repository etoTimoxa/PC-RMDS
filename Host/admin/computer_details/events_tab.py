"""Вкладка "События" - просмотр системных событий"""

from qtpy.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView
from qtpy.QtCore import Qt


class EventsTab(QWidget):
    """Вкладка с системными событиями"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_events = []
        self.event_statistics = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Тип события:"))
        
        self.event_type_filter = QComboBox()
        self.event_type_filter.addItems([
            "Все", "system_boot", "shutdown", "restart", 
            "windows_event", "user_action", "windows_restart", "sleep"
        ])
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
    
    def update_events(self, events, statistics):
        """Обновляет события"""
        self.all_events = events
        self.event_statistics = statistics
        self.filter_events()
    
    def filter_events(self):
        filter_type = self.event_type_filter.currentText()
        
        filtered = self.all_events
        if filter_type != "Все":
            filtered = [e for e in self.all_events 
                       if e.get('type') == filter_type or 
                       e.get('data', {}).get('action_type') == filter_type]
        
        self.events_table.setRowCount(len(filtered))
        
        for row, event in enumerate(filtered):
            timestamp = event.get('timestamp', '')[:19]
            event_type = event.get('type', event.get('data', {}).get('action_type', 'unknown'))
            description = self._get_event_description(event)
            
            self.events_table.setItem(row, 0, QTableWidgetItem(timestamp))
            self.events_table.setItem(row, 1, QTableWidgetItem(event_type))
            self.events_table.setItem(row, 2, QTableWidgetItem(description))
    
    def _get_event_description(self, event):
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
    
    def get_all_events(self):
        return self.all_events
    
    def get_event_statistics(self):
        return self.event_statistics