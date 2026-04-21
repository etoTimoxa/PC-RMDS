"""Вкладка "Метрики" - просмотр метрик производительности"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt


class MetricsTab(QWidget):
    """Вкладка с метриками производительности"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.current_metrics = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(6)
        self.metrics_table.setHorizontalHeaderLabels([
            "Время", "CPU, %", "RAM, %", "RAM, GB", "Disk, %", "Network, MB/s"
        ])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.metrics_table)
    
    def update_metrics(self, metrics):
        """Обновляет таблицу метрик"""
        self.current_metrics = metrics
        self.metrics_table.setRowCount(len(metrics))
        
        for row, metric in enumerate(metrics):
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
    
    def get_current_metrics(self):
        return self.current_metrics