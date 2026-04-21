"""Вкладка "Аномалии" - просмотр аномалий нагрузки"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt


class AnomaliesTab(QWidget):
    """Вкладка с аномалиями"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.anomalies = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
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
        self.refresh_anomalies_btn.clicked.connect(lambda: self.parent_window.load_anomalies() if self.parent_window else None)
        threshold_layout.addWidget(self.refresh_anomalies_btn)
        
        threshold_layout.addStretch()
        layout.addLayout(threshold_layout)
        
        self.anomalies_table = QTableWidget()
        self.anomalies_table.setColumnCount(4)
        self.anomalies_table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "Тип аномалии"])
        self.anomalies_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.anomalies_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.anomalies_table)
    
    def update_anomalies(self, anomalies, cpu_thresh, ram_thresh):
        """Обновляет таблицу аномалий"""
        self.anomalies = anomalies
        self.anomalies_table.setRowCount(len(anomalies))
        
        for row, anomaly in enumerate(anomalies):
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
    
    def get_thresholds(self):
        return int(self.cpu_threshold.currentText()), int(self.ram_threshold.currentText())