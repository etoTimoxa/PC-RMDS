"""Вкладка "Отчеты" - общие отчеты по всем компьютерам"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from qtpy.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QComboBox, QPushButton, QScrollArea,
                             QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                             QFileDialog, QMessageBox, QDateEdit)
from qtpy.QtCore import Qt, QDate

from core.api_client import APIClient as DatabaseManager
from admin.computer_details.widgets import DateRangeWidget

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
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
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
    """Вкладка с общими отчетами по всем компьютерам"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.all_computers = []
        self.groups = []
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
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
        
        # Выбор группы
        control_layout.addWidget(QLabel("Группа компьютеров:"), 0, 0)
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(200)
        control_layout.addWidget(self.group_combo, 0, 1)
        
        # Тип отчета
        control_layout.addWidget(QLabel("Тип отчета:"), 0, 2)
        self.report_type = QComboBox()
        self.report_type.addItems([
            "📊 Свободное место на дисках",
            "📈 Средние показатели производительности",
            "📊 Статус онлайн/оффлайн",
            "📈 Статистика по операционным системам",
            "📋 Отчет по железу",
            "⏱️ Время работы компьютеров"
        ])
        self.report_type.setMinimumWidth(300)
        control_layout.addWidget(self.report_type, 0, 3)
        
        # Вид отчета
        control_layout.addWidget(QLabel("Вид:"), 0, 4)
        self.report_view_type = QComboBox()
        self.report_view_type.addItems(["Таблица", "Гистограмма", "Круговая диаграмма"])
        self.report_view_type.setMinimumWidth(150)
        control_layout.addWidget(self.report_view_type, 0, 5)
        
        # Период отчета
        self.date_range = DateRangeWidget()
        control_layout.addWidget(self.date_range, 1, 0, 1, 2)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("🔄 Сформировать отчет")
        self.generate_btn.setMinimumHeight(35)
        self.generate_btn.setMinimumWidth(180)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff8c42;
                border-radius: 6px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        self.generate_btn.clicked.connect(self.generate_report)
        button_layout.addWidget(self.generate_btn)
        
        self.export_pdf_btn = QPushButton("📄 Экспорт в PDF")
        self.export_pdf_btn.setMinimumHeight(35)
        self.export_pdf_btn.setMinimumWidth(180)
        self.export_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                border-radius: 6px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        self.export_pdf_btn.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(self.export_pdf_btn)
        
        control_layout.addLayout(button_layout, 1, 2, 1, 2)
        
        layout.addWidget(control_panel)
        
        # Область отчета
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
    
    def load_data(self):
        """Загружает список компьютеров и групп"""
        try:
            # Загружаем компьютеры
            computers_result = DatabaseManager.get_computers()
            if isinstance(computers_result, dict) and 'computers' in computers_result:
                self.all_computers = computers_result['computers']
            elif isinstance(computers_result, list):
                self.all_computers = computers_result
            
            # Загружаем группы
            groups_result = DatabaseManager.get_computer_groups()
            if groups_result:
                self.groups = groups_result
            
            # Заполняем комбобокс групп
            self.group_combo.clear()
            self.group_combo.addItem("Все компьютеры", None)
            for group in self.groups:
                self.group_combo.addItem(group['group_name'], group['group_id'])
                
        except Exception as e:
            print(f"Ошибка загрузки данных для отчетов: {e}")
    
    def get_filtered_computers(self):
        """Возвращает отфильтрованный список компьютеров по выбранной группе"""
        selected_group_id = self.group_combo.currentData()
        
        if selected_group_id is None:
            return self.all_computers
        
        return [c for c in self.all_computers if c.get('group_id') == selected_group_id]
    
    def generate_report(self):
        """Формирует выбранный отчет"""
        self.clear_report_area()
        
        computers = self.get_filtered_computers()
        report_type = self.report_type.currentText()
        
        if not computers:
            self._show_no_data_error("Нет компьютеров для формирования отчета")
            return
        
        # Заголовок отчета
        title = QLabel(f"{report_type}\nКомпьютеров в отчете: {len(computers)}")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #ff8c42;
            padding: 10px;
            border-bottom: 2px solid #ff8c42;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(title)
        
        # Генерация отчета по типу
        if "Свободное место на дисках" in report_type:
            self._generate_disk_space_report(computers)
        elif "Средние показатели" in report_type:
            self._generate_average_metrics_report(computers)
        elif "Статус онлайн" in report_type:
            self._generate_online_status_report(computers)
        elif "операционным системам" in report_type:
            self._generate_os_report(computers)
        elif "Отчет по железу" in report_type:
            self._generate_hardware_report(computers)
        elif "Время работы" in report_type:
            self._generate_uptime_report(computers)
    
    def _generate_disk_space_report(self, computers):
        """Отчет по свободному месту на дисках"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Компьютер", "Всего, ГБ", "Использовано, ГБ", "Свободно, ГБ", "Статус"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
            used = float(comp.get('storage_used', 0)) if comp.get('storage_used') else 0
            free = total - used if total else 0
            
            # Определяем статус
            status = "✅ Нормально"
            status_color = "#27ae60"
            
            if total and free / total < 0.1:  # Меньше 10% свободно
                status = "⚠️ Нужно почистить!"
                status_color = "#e74c3c"
            elif total and free / total < 0.2:  # Меньше 20% свободно
                status = "⚠️ Мало места"
                status_color = "#f39c12"
            
            status_item = QTableWidgetItem(status)
            status_item.setForeground(Qt.GlobalColor.white if status != "✅ Нормально" else Qt.GlobalColor.black)
            status_item.setBackground(Qt.GlobalColor.red if status == "⚠️ Нужно почистить!" else Qt.GlobalColor.yellow if status == "⚠️ Мало места" else Qt.GlobalColor.green)
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(f"{total:.1f}" if total else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{used:.1f}" if used else "—"))
            table.setItem(row, 3, QTableWidgetItem(f"{free:.1f}" if total else "—"))
            table.setItem(row, 4, status_item)
        
        self.report_container_layout.addWidget(table)
        
        # Добавляем график если доступен matplotlib
        if MATPLOTLIB_AVAILABLE:
            self._create_disk_space_chart(computers)
    
    def _generate_average_metrics_report(self, computers):
        """Отчет по средним показателям производительности"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Компьютер", "CPU среднее, %", "RAM среднее, %", "Disk среднее, %", "Network, МБ/с", "Количество замеров"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            
            avg_cpu = comp.get('avg_cpu', 0)
            avg_ram = comp.get('avg_ram', 0)
            avg_disk = comp.get('avg_disk', 0)
            network = comp.get('network_total', 0)
            measurements = comp.get('measurement_count', 0)
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(f"{avg_cpu:.1f}" if avg_cpu else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{avg_ram:.1f}" if avg_ram else "—"))
            table.setItem(row, 3, QTableWidgetItem(f"{avg_disk:.1f}" if avg_disk else "—"))
            table.setItem(row, 4, QTableWidgetItem(f"{network:.2f}" if network else "—"))
            table.setItem(row, 5, QTableWidgetItem(str(measurements) if measurements else "—"))
        
        self.report_container_layout.addWidget(table)
    
    def _generate_online_status_report(self, computers):
        """Отчет по статусу онлайн/оффлайн"""
        online = sum(1 for c in computers if c.get('is_online'))
        offline = len(computers) - online
        
        stats_label = QLabel(f"✅ Онлайн: {online} | ❌ Оффлайн: {offline}")
        stats_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(stats_label)
        
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Компьютер", "Статус", "Последний онлайн", "Пользователь"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            is_online = comp.get('is_online')
            last_online = comp.get('last_online', 'Никогда')
            user = comp.get('full_name', 'Не назначен')
            
            status_text = "✅ Онлайн" if is_online else "❌ Оффлайн"
            status_color = "#27ae60" if is_online else "#e74c3c"
            
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(Qt.GlobalColor(status_color))
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, status_item)
            table.setItem(row, 2, QTableWidgetItem(str(last_online)[:19] if last_online else "Никогда"))
            table.setItem(row, 3, QTableWidgetItem(user))
        
        self.report_container_layout.addWidget(table)
        
        # Круговая диаграмма
        if MATPLOTLIB_AVAILABLE:
            self._create_online_pie_chart(online, offline)
    
    def _generate_os_report(self, computers):
        """Статистика по операционным системам"""
        os_stats = {}
        for comp in computers:
            os_name = comp.get('os_name', 'Неизвестно')
            os_stats[os_name] = os_stats.get(os_name, 0) + 1
        
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Операционная система", "Количество компьютеров"])
        table.setRowCount(len(os_stats))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, (os_name, count) in enumerate(os_stats.items()):
            table.setItem(row, 0, QTableWidgetItem(os_name))
            table.setItem(row, 1, QTableWidgetItem(str(count)))
        
        self.report_container_layout.addWidget(table)
        
        if MATPLOTLIB_AVAILABLE:
            self._create_os_pie_chart(os_stats)
    
    def _generate_hardware_report(self, computers):
        """Отчет по конфигурациям железа"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            cpu = comp.get('cpu_model', 'Unknown')
            cores = comp.get('cpu_cores', 0)
            ram = comp.get('ram_total', 0)
            gpu = comp.get('gpu_model', 'Unknown')
            disk = comp.get('storage_total', 0)
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(cpu))
            table.setItem(row, 2, QTableWidgetItem(str(cores) if cores else "—"))
            table.setItem(row, 3, QTableWidgetItem(f"{ram:.1f}" if ram else "—"))
            table.setItem(row, 4, QTableWidgetItem(gpu))
            table.setItem(row, 5, QTableWidgetItem(f"{disk:.1f}" if disk else "—"))
        
        self.report_container_layout.addWidget(table)
    
    def _generate_uptime_report(self, computers):
        """Отчет по времени работы компьютеров"""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Компьютер", "Общее время работы", "Активность за 7 дней", "Количество сессий"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            total_uptime = comp.get('total_uptime', 0)
            activity_7d = comp.get('activity_7d', 0)
            session_count = comp.get('session_count', 0)
            
            # Переводим в часы
            total_hours = total_uptime / 3600 if total_uptime else 0
            activity_hours = activity_7d / 3600 if activity_7d else 0
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(f"{total_hours:.1f} ч" if total_hours else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{activity_hours:.1f} ч" if activity_hours else "—"))
            table.setItem(row, 3, QTableWidgetItem(str(session_count) if session_count else "—"))
        
        self.report_container_layout.addWidget(table)
    
    def _create_disk_space_chart(self, computers):
        """Создает график свободного места"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = []
        free_space = []
        colors = []
        
        for comp in computers[:20]:  # Ограничиваем 20 компов для графика
            hostname = comp.get('hostname', 'Unknown')[:12]
            total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
            used = float(comp.get('storage_used', 0)) if comp.get('storage_used') else 0
            free = total - used if total else 0
            
            hostnames.append(hostname)
            free_space.append(free)
            
            if total and free / total < 0.1:
                colors.append('#e74c3c')
            elif total and free / total < 0.2:
                colors.append('#f39c12')
            else:
                colors.append('#27ae60')
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        bars = ax.bar(hostnames, free_space, color=colors, edgecolor='white')
        ax.set_title("Свободное место на дисках, ГБ", fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_online_pie_chart(self, online, offline):
        """Круговая диаграмма статусов онлайн"""
        figure = Figure(figsize=(6, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        ax.pie([online, offline], labels=['Онлайн', 'Оффлайн'],
               colors=['#27ae60', '#e74c3c'], autopct='%1.1f%%', startangle=90)
        ax.set_title("Статус компьютеров", fontsize=14, fontweight='bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_os_pie_chart(self, os_stats):
        """Круговая диаграмма по ОС"""
        figure = Figure(figsize=(8, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        values = list(os_stats.values())
        labels = list(os_stats.keys())
        colors = ['#3498db', '#2ecc71', '#9b59b6', '#e74c3c', '#f39c12', '#1abc9c']
        
        ax.pie(values, labels=labels, colors=colors[:len(values)],
               autopct='%1.1f%%', startangle=90)
        ax.set_title("Распределение по операционным системам", fontsize=14, fontweight='bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def clear_report_area(self):
        while self.report_container_layout.count():
            child = self.report_container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _show_no_data_error(self, message="Нет данных для отображения"):
        error_label = QLabel(message)
        error_label.setStyleSheet("color: #7f8c8d; padding: 50px; font-size: 16px;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(error_label)
    
    def export_to_pdf(self):
        """Экспортирует сформированный отчет в PDF"""
        if not REPORTLAB_AVAILABLE:
            QMessageBox.warning(self, "Ошибка", "Библиотека ReportLab не установлена.\nУстановите: pip install reportlab")
            return
        
        # Получаем документы пользователя
        documents_path = Path.home() / "Documents"
        reports_path = documents_path / "PC-RMDS_Reports"
        reports_path.mkdir(parents=True, exist_ok=True)
        
        report_type = self.report_type.currentText().replace("📊", "").replace("📈", "").replace("📋", "").replace("⏱️", "").strip()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет", 
            str(reports_path / f"general_report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"),
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
            
            period = self.date_range.get_period()
            title = Paragraph(f"Общий отчет: {report_type}", title_style)
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            story.append(Paragraph(f"Период: {period.get('from', '')} — {period.get('to', '')}", normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            computers = self.get_filtered_computers()
            
            if "Свободное место на дисках" in report_type:
                story.append(Paragraph("Отчет по свободному месту на дисках:", heading_style))
                
                table_data = [["Компьютер", "Всего, ГБ", "Использовано, ГБ", "Свободно, ГБ", "Статус"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
                    used = float(comp.get('storage_used', 0)) if comp.get('storage_used') else 0
                    free = total - used if total else 0
                    
                    status = "✅ Нормально"
                    if total and free / total < 0.1:
                        status = "⚠️ Нужно почистить!"
                    elif total and free / total < 0.2:
                        status = "⚠️ Мало места"
                    
                    table_data.append([
                        hostname,
                        f"{total:.1f}" if total else "—",
                        f"{used:.1f}" if used else "—",
                        f"{free:.1f}" if total else "—",
                        status
                    ])
                
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
            
            elif "Статус онлайн" in report_type:
                online = sum(1 for c in computers if c.get('is_online'))
                offline = len(computers) - online
                
                story.append(Paragraph(f"✅ Онлайн: {online} | ❌ Оффлайн: {offline}", normal_style))
                story.append(Spacer(1, 0.2*inch))
                
                table_data = [["Компьютер", "Статус", "Последний онлайн", "Пользователь"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    is_online = comp.get('is_online')
                    last_online = comp.get('last_online', 'Никогда')
                    user = comp.get('full_name', 'Не назначен')
                    
                    status_text = "✅ Онлайн" if is_online else "❌ Оффлайн"
                    table_data.append([
                        hostname,
                        status_text,
                        str(last_online)[:19] if last_online else "Никогда",
                        user
                    ])
                
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
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
            
            elif "операционным системам" in report_type:
                os_stats = {}
                for comp in computers:
                    os_name = comp.get('os_name', 'Неизвестно')
                    os_stats[os_name] = os_stats.get(os_name, 0) + 1
                
                table_data = [["Операционная система", "Количество компьютеров"]]
                for os_name, count in os_stats.items():
                    table_data.append([os_name, str(count)])
                
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
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
            
            elif "Отчет по железу" in report_type:
                table_data = [["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    cpu = comp.get('cpu_model', 'Unknown')
                    cores = comp.get('cpu_cores', 0)
                    ram = comp.get('ram_total', 0)
                    gpu = comp.get('gpu_model', 'Unknown')
                    disk = comp.get('storage_total', 0)
                    
                    table_data.append([
                        hostname,
                        cpu,
                        str(cores) if cores else "—",
                        f"{ram:.1f}" if ram else "—",
                        gpu,
                        f"{disk:.1f}" if disk else "—"
                    ])
                
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9b59b6')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'RussianFont'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'RussianFont'),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                ]))
                story.append(table)
            
            doc.build(story)
            QMessageBox.information(self, "Успех", f"Отчет сохранен в:\n{file_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка при создании PDF: {str(e)}")
