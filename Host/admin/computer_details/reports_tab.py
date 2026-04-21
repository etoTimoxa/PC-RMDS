"""Вкладка "Отчеты" - формирование отчетов и экспорт в PDF"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QLabel, QComboBox, QPushButton, QScrollArea,
                            QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                            QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt

from core.api_client import APIClient
from .widgets import get_app_icon

# Попытка импортировать matplotlib для графиков
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Попытка импортировать reportlab для PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab.rl_config
    reportlab.rl_config.warnOnMissingFontGlyphs = 0
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ReportsTab(QWidget):
    """Вкладка с отчетами"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
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
        
        control_layout.addWidget(QLabel("Тип данных:"), 0, 0)
        self.report_data_type = QComboBox()
        self.report_data_type.addItems(["Метрики", "События", "Аномалии"])
        self.report_data_type.setMinimumWidth(150)
        self.report_data_type.currentTextChanged.connect(self.on_data_type_changed)
        control_layout.addWidget(self.report_data_type, 0, 1)
        
        control_layout.addWidget(QLabel("Показатель:"), 0, 2)
        self.report_metric = QComboBox()
        self.report_metric.addItems(["Все метрики", "CPU, %", "RAM, %", "Disk, %", "Network, MB/s"])
        self.report_metric.setMinimumWidth(120)
        control_layout.addWidget(self.report_metric, 0, 3)
        
        control_layout.addWidget(QLabel("Вид:"), 1, 0)
        self.report_view_type = QComboBox()
        self.report_view_type.setMinimumWidth(150)
        control_layout.addWidget(self.report_view_type, 1, 1)
        
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
            QPushButton:hover { background-color: #e67e22; }
        """)
        self.generate_btn.clicked.connect(self.generate_report)
        button_layout.addWidget(self.generate_btn)
        
        self.export_pdf_btn = QPushButton("📄 Экспорт в PDF")
        self.export_pdf_btn.setMinimumHeight(35)
        self.export_pdf_btn.setMinimumWidth(150)
        self.export_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        self.export_pdf_btn.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(self.export_pdf_btn)
        
        control_layout.addLayout(button_layout, 1, 2, 1, 2)
        
        self.on_data_type_changed(self.report_data_type.currentText())
        
        layout.addWidget(control_panel)
        
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
    
    def on_data_type_changed(self, data_type):
        self.report_metric.setVisible(data_type == "Метрики")
        
        if data_type == "События":
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Круговая диаграмма"])
        elif data_type == "Аномалии":
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Гистограмма"])
        else:
            self.report_view_type.clear()
            self.report_view_type.addItems(["Таблица", "Гистограмма", "Линейный график"])
    
    def generate_report(self):
        """Формирует отчет на основе текущих данных"""
        data_type = self.report_data_type.currentText()
        view_type = self.report_view_type.currentText()
        
        self.clear_report_area()
        
        period = self.parent_window.date_range.get_period() if self.parent_window else {}
        hostname = self.parent_window.hostname if self.parent_window else "Unknown"
        
        title = QLabel(f"Отчет: {data_type}\nПериод: {period.get('from', '')} — {period.get('to', '')}")
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
            self._generate_metrics_report(view_type)
        elif data_type == "События":
            self._generate_events_report(view_type)
        elif data_type == "Аномалии":
            self._generate_anomalies_report(view_type)
    
    def _generate_metrics_report(self, view_type):
        metrics = self.parent_window.metrics_tab.get_current_metrics() if self.parent_window else []
        
        if not metrics:
            self._show_no_data_error()
            return
        
        selected_metric = self.report_metric.currentText()
        
        if view_type == "Таблица":
            self._create_metrics_table(metrics, selected_metric)
        elif view_type == "Гистограмма":
            self._create_metrics_histogram(metrics, selected_metric)
        elif view_type == "Линейный график":
            self._create_metrics_line_chart(metrics, selected_metric)
    
    def _generate_events_report(self, view_type):
        statistics = self.parent_window.events_tab.get_event_statistics() if self.parent_window else {}
        
        if not statistics:
            self._show_no_data_error()
            return
        
        if view_type == "Таблица":
            self._create_events_table(statistics)
        elif view_type == "Круговая диаграмма":
            self._create_events_pie_chart(statistics)
    
    def _generate_anomalies_report(self, view_type):
        anomalies = self.parent_window.anomalies_tab.anomalies if self.parent_window else []
        
        if not anomalies:
            self._show_no_data_error()
            return
        
        if view_type == "Таблица":
            self._create_anomalies_table(anomalies)
        elif view_type == "Гистограмма":
            self._create_anomalies_histogram(anomalies)
    
    def _create_metrics_table(self, metrics, selected_metric):
        if selected_metric == "Все метрики":
            table = QTableWidget()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "RAM, GB", "Disk, %", "Network, MB/s"])
            table.setRowCount(len(metrics))
        else:
            metric_map = {
                "CPU, %": "cpu_usage",
                "RAM, %": "ram_usage", 
                "Disk, %": "disk_usage",
                "Network, MB/s": "network"
            }
            metric_key = metric_map.get(selected_metric, "cpu_usage")
            
            table = QTableWidget()
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["Время", selected_metric])
            table.setRowCount(len(metrics))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, metric in enumerate(metrics):
            timestamp = metric.get('timestamp', '')[:19]
            
            if selected_metric == "Все метрики":
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
            else:
                if selected_metric == "Network, MB/s":
                    value = metric.get('network_sent_mb', 0) + metric.get('network_recv_mb', 0)
                    value_str = f"{value:.2f}"
                else:
                    value = metric.get(metric_key, 0)
                    value_str = f"{value:.1f}" if value else "—"
                
                table.setItem(row, 0, QTableWidgetItem(timestamp))
                table.setItem(row, 1, QTableWidgetItem(value_str))
        
        self.report_container_layout.addWidget(table)
    
    def _create_metrics_histogram(self, metrics, selected_metric):
        if not MATPLOTLIB_AVAILABLE:
            self._show_matplotlib_error()
            return
        
        # Группируем по дням
        daily_data = {}
        for m in metrics:
            date_str = m.get('timestamp', '')[:10]
            if selected_metric == "Network, MB/s":
                value = m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0)
            elif selected_metric == "Все метрики":
                value = m.get('cpu_usage', 0)
            else:
                metric_map = {"CPU, %": "cpu_usage", "RAM, %": "ram_usage", "Disk, %": "disk_usage"}
                value = m.get(metric_map.get(selected_metric, "cpu_usage"), 0)
            
            if date_str not in daily_data:
                daily_data[date_str] = []
            daily_data[date_str].append(value)
        
        categories = []
        values = []
        for date_str, vals in daily_data.items():
            categories.append(date_str)
            values.append(sum(vals) / len(vals))
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        bars = ax.bar(categories, values, color='#ff8c42', edgecolor='white', linewidth=2)
        ax.set_title(f"Средний {selected_metric} по дням", fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.annotate(f'{value:.1f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_metrics_line_chart(self, metrics, selected_metric):
        if not MATPLOTLIB_AVAILABLE:
            self._show_matplotlib_error()
            return
        
        timestamps = [m.get('timestamp', '')[:16] for m in metrics[:100]]
        
        if selected_metric == "Все метрики":
            cpu_vals = [m.get('cpu_usage', 0) for m in metrics[:100]]
            ram_vals = [m.get('ram_usage', 0) for m in metrics[:100]]
            disk_vals = [m.get('disk_usage', 0) for m in metrics[:100]]
            network_vals = [m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0) for m in metrics[:100]]
            
            figure = Figure(figsize=(10, 5), facecolor='white')
            canvas = FigureCanvas(figure)
            ax = figure.add_subplot(111)
            
            ax.plot(timestamps, cpu_vals, color='#3498db', linewidth=2, marker='o', markersize=3, label='CPU, %')
            ax.plot(timestamps, ram_vals, color='#2ecc71', linewidth=2, marker='s', markersize=3, label='RAM, %')
            ax.plot(timestamps, disk_vals, color='#9b59b6', linewidth=2, marker='^', markersize=3, label='Disk, %')
            
            ax2 = ax.twinx()
            ax2.plot(timestamps, network_vals, color='#e74c3c', linewidth=2, marker='d', markersize=3, label='Network, MB/s')
            ax2.set_ylabel('Network, MB/s', color='#e74c3c')
            
            ax.set_title("Динамика метрик", fontsize=14, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3)
            
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=8)
        else:
            metric_map = {"CPU, %": "cpu_usage", "RAM, %": "ram_usage", "Disk, %": "disk_usage"}
            if selected_metric == "Network, MB/s":
                values = [m.get('network_sent_mb', 0) + m.get('network_recv_mb', 0) for m in metrics[:100]]
            else:
                values = [m.get(metric_map.get(selected_metric, "cpu_usage"), 0) for m in metrics[:100]]
            
            figure = Figure(figsize=(10, 5), facecolor='white')
            canvas = FigureCanvas(figure)
            ax = figure.add_subplot(111)
            
            ax.plot(timestamps, values, color='#ff8c42', linewidth=2, marker='o', markersize=3)
            ax.set_title(f"Динамика {selected_metric}", fontsize=14, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_events_table(self, statistics):
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Тип события", "Количество"])
        table.setRowCount(len(statistics))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, (event_type, count) in enumerate(statistics.items()):
            table.setItem(row, 0, QTableWidgetItem(event_type))
            table.setItem(row, 1, QTableWidgetItem(str(count)))
        
        self.report_container_layout.addWidget(table)
    
    def _create_events_pie_chart(self, statistics):
        if not MATPLOTLIB_AVAILABLE:
            self._show_matplotlib_error()
            return
        
        figure = Figure(figsize=(8, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        categories = list(statistics.keys())
        values = list(statistics.values())
        colors = ['#ff8c42', '#2ecc71', '#3498db', '#9b59b6', '#e74c3c', '#1abc9c', '#f39c12']
        
        wedges, texts, autotexts = ax.pie(values, labels=categories, autopct='%1.1f%%',
                                          colors=colors[:len(categories)], startangle=90)
        ax.set_title("Распределение событий по типам", fontsize=14, fontweight='bold')
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_anomalies_table(self, anomalies):
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Время", "CPU, %", "RAM, %", "Тип"])
        table.setRowCount(len(anomalies))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        cpu_thresh, ram_thresh = self.parent_window.anomalies_tab.get_thresholds() if self.parent_window else (90, 90)
        
        for row, anomaly in enumerate(anomalies):
            timestamp = anomaly.get('timestamp', '')[:19]
            cpu = anomaly.get('cpu_usage')
            ram = anomaly.get('ram_usage')
            
            anomaly_type = []
            if cpu and cpu > cpu_thresh:
                anomaly_type.append("CPU")
            if ram and ram > ram_thresh:
                anomaly_type.append("RAM")
            
            table.setItem(row, 0, QTableWidgetItem(timestamp))
            table.setItem(row, 1, QTableWidgetItem(f"{cpu:.1f}" if cpu else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{ram:.1f}" if ram else "—"))
            table.setItem(row, 3, QTableWidgetItem(", ".join(anomaly_type) if anomaly_type else "Высокая нагрузка"))
        
        self.report_container_layout.addWidget(table)
    
    def _create_anomalies_histogram(self, anomalies):
        if not MATPLOTLIB_AVAILABLE:
            self._show_matplotlib_error()
            return
        
        daily_anomalies = {}
        for anomaly in anomalies:
            date_str = anomaly.get('timestamp', '')[:10]
            if date_str:
                daily_anomalies[date_str] = daily_anomalies.get(date_str, 0) + 1
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        categories = list(daily_anomalies.keys())
        values = list(daily_anomalies.values())
        
        bars = ax.bar(categories, values, color='#e74c3c', edgecolor='white', linewidth=2)
        ax.set_title("Количество аномалий по дням", fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax.annotate(str(value), xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def export_to_pdf(self):
        """Экспортирует сформированный отчет в PDF"""
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "Ошибка", "Библиотека ReportLab не установлена.\nУстановите: pip install reportlab")
            return
        
        # Получаем документы пользователя
        documents_path = Path.home() / "Documents"
        reports_path = documents_path / "PC-RMDS_Reports"
        reports_path.mkdir(parents=True, exist_ok=True)
        
        hostname = self.parent_window.hostname if self.parent_window else "Unknown"
        data_type = self.report_data_type.currentText()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет", 
            str(reports_path / f"report_{hostname}_{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"),
            "PDF files (*.pdf)"
        )
        
        if not file_path:
            return
        
        try:
            # Регистрируем шрифт для кириллицы
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/tahoma.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('RussianFont', font_path))
                        break
                    except:
                        continue
            
            doc = SimpleDocTemplate(file_path, pagesize=A4,
                                   rightMargin=72, leftMargin=72,
                                   topMargin=72, bottomMargin=72)
            
            story = []
            
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                         fontSize=16, textColor=colors.HexColor('#ff8c42'),
                                         alignment=1, fontName='RussianFont')
            heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                           fontSize=12, textColor=colors.HexColor('#2c3e50'),
                                           spaceAfter=10, fontName='RussianFont')
            normal_style = ParagraphStyle('Normal', parent=styles['Normal'],
                                          fontSize=9, fontName='RussianFont')
            
            period = self.parent_window.date_range.get_period() if self.parent_window else {}
            title = Paragraph(f"Отчет по компьютеру: {hostname}", title_style)
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            story.append(Paragraph(f"Тип отчета: {data_type}", normal_style))
            story.append(Paragraph(f"Период: {period.get('from', '')} — {period.get('to', '')}", normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Добавляем данные в отчет
            if data_type == "Метрики":
                metrics = self.parent_window.metrics_tab.get_current_metrics() if self.parent_window else []
                if metrics:
                    story.append(Paragraph("Таблица метрик:", heading_style))
                    
                    table_data = [["Время", "CPU, %", "RAM, %", "RAM, GB", "Disk, %", "Network, MB/s"]]
                    for metric in metrics[:50]:  # Ограничиваем 50 записей для PDF
                        timestamp = metric.get('timestamp', '')[:19]
                        cpu = f"{metric.get('cpu_usage', 0):.1f}" if metric.get('cpu_usage') else "—"
                        ram_percent = f"{metric.get('ram_usage', 0):.1f}" if metric.get('ram_usage') else "—"
                        ram_gb = f"{metric.get('ram_used_gb', 0):.1f}" if metric.get('ram_used_gb') else "—"
                        disk = f"{metric.get('disk_usage', 0):.1f}" if metric.get('disk_usage') else "—"
                        network = metric.get('network_sent_mb', 0) + metric.get('network_recv_mb', 0)
                        network_str = f"{network:.2f}" if network else "—"
                        
                        table_data.append([timestamp, cpu, ram_percent, ram_gb, disk, network_str])
                    
                    table = Table(table_data, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff8c42')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'RussianFont'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('FONTNAME', (0, 1), (-1, -1), 'RussianFont'),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 0.2*inch))
            
            elif data_type == "События":
                statistics = self.parent_window.events_tab.get_event_statistics() if self.parent_window else {}
                if statistics:
                    story.append(Paragraph("Статистика событий:", heading_style))
                    
                    table_data = [["Тип события", "Количество"]]
                    for event_type, count in statistics.items():
                        table_data.append([event_type, str(count)])
                    
                    table = Table(table_data, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff8c42')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'RussianFont'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('FONTNAME', (0, 1), (-1, -1), 'RussianFont'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 0.2*inch))
            
            elif data_type == "Аномалии":
                anomalies = self.parent_window.anomalies_tab.anomalies if self.parent_window else []
                cpu_thresh, ram_thresh = self.parent_window.anomalies_tab.get_thresholds() if self.parent_window else (90, 90)
                
                if anomalies:
                    story.append(Paragraph("Обнаруженные аномалии:", heading_style))
                    
                    table_data = [["Время", "CPU, %", "RAM, %", "Тип аномалии"]]
                    for anomaly in anomalies[:50]:  # Ограничиваем 50 записей
                        timestamp = anomaly.get('timestamp', '')[:19]
                        cpu = f"{anomaly.get('cpu_usage', 0):.1f}" if anomaly.get('cpu_usage') else "—"
                        ram = f"{anomaly.get('ram_usage', 0):.1f}" if anomaly.get('ram_usage') else "—"
                        
                        anomaly_type = []
                        cpu_val = anomaly.get('cpu_usage', 0)
                        ram_val = anomaly.get('ram_usage', 0)
                        if cpu_val and isinstance(cpu_val, (int, float)) and cpu_val > cpu_thresh:
                            anomaly_type.append(f"CPU > {cpu_thresh}%")
                        if ram_val and isinstance(ram_val, (int, float)) and ram_val > ram_thresh:
                            anomaly_type.append(f"RAM > {ram_thresh}%")
                        
                        type_str = ", ".join(anomaly_type) if anomaly_type else "Высокая нагрузка"
                        table_data.append([timestamp, cpu, ram, type_str])
                    
                    table = Table(table_data, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'RussianFont'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('FONTNAME', (0, 1), (-1, -1), 'RussianFont'),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ]))
                    story.append(table)
            
            doc.build(story)
            QMessageBox.information(self, "Успех", f"Отчет сохранен в:\n{file_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка при создании PDF: {str(e)}")
    
    def clear_report_area(self):
        while self.report_container_layout.count():
            child = self.report_container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _show_no_data_error(self):
        error_label = QLabel("Нет данных за выбранный период")
        error_label.setStyleSheet("color: red; padding: 20px;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(error_label)
    
    def _show_matplotlib_error(self):
        error_label = QLabel(
            "Для отображения графиков установите matplotlib:\n"
            "pip install matplotlib\n\n"
            "Или используйте табличный вид отчета"
        )
        error_label.setStyleSheet("color: orange; padding: 20px; background-color: #f8f9fa; border-radius: 8px;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(error_label)