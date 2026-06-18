"""Вкладка "Отчеты" - общие отчеты по всем компьютерам"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from io import BytesIO
from email.utils import parsedate_to_datetime
from qtpy.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QComboBox, QPushButton, QScrollArea,
                             QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
                             QFileDialog, QMessageBox, QDateEdit, QProgressBar, QApplication)
from qtpy.QtCore import Qt, QDate, QTimer
from qtpy.QtGui import QColor

from core.api_client import APIClient
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
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
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
        self._current_figure = None  # Храним текущую фигуру для экспорта
        self.init_ui()
        self.load_data()
        
        # Подключаем сигнал изменения типа отчета для обновления доступных видов
        self.report_type.currentTextChanged.connect(self.update_available_view_types)
        self.update_available_view_types()
    
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
            "Свободное место на дисках",
            "Средние показатели производительности",
            "Статистика по операционным системам",
            "Отчет по железу",
            "Время работы компьютеров"
        ])
        self.report_type.setMinimumWidth(300)
        control_layout.addWidget(self.report_type, 0, 3)
        
        # Вид отчета
        control_layout.addWidget(QLabel("Вид:"), 0, 4)
        self.report_view_type = QComboBox()
        self.report_view_type.setMinimumWidth(150)
        control_layout.addWidget(self.report_view_type, 0, 5)
        
        # Период отчета
        self.date_range = DateRangeWidget()
        control_layout.addWidget(self.date_range, 1, 0, 1, 2)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("Сформировать отчет")
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
        
        self.export_pdf_btn = QPushButton("Экспорт в PDF")
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
    
    def update_available_view_types(self):
        """Обновляет доступные виды отображения в зависимости от типа отчета"""
        self.report_view_type.blockSignals(True)
        self.report_view_type.clear()
        
        report_type = self.report_type.currentText()
        
        if "Свободное место на дисках" in report_type:
            items = ["Таблица"]
            if MATPLOTLIB_AVAILABLE:
                items.append("Гистограмма")
            self.report_view_type.addItems(items)
            
        elif "Средние показатели" in report_type:
            items = ["Таблица"]
            if MATPLOTLIB_AVAILABLE:
                items.append("Гистограмма")
            self.report_view_type.addItems(items)
            
        elif "операционным системам" in report_type:
            # Только круговая диаграмма для статистики по ОС
            if MATPLOTLIB_AVAILABLE:
                self.report_view_type.addItems(["Круговая диаграмма"])
            
        elif "Отчет по железу" in report_type:
            items = ["Таблица"]
            if MATPLOTLIB_AVAILABLE:
                items.append("Гистограмма")
            self.report_view_type.addItems(items)
            
        elif "Время работы" in report_type:
            # Только таблица для этого отчета
            self.report_view_type.addItems(["Таблица"])
        
        self.report_view_type.blockSignals(False)
    
    def load_data(self):
        """Загружает список компьютеров и групп"""
        try:
            # Загружаем компьютеры
            result = APIClient.get('/computers')
            if result and result.get('success'):
                computers_data = result.get('data', {})
                self.all_computers = computers_data.get('computers', [])
            else:
                self.all_computers = []
            
            # Загружаем группы
            groups_result = APIClient.get('/computers/groups')
            if groups_result and groups_result.get('success'):
                self.groups = groups_result.get('data', [])
            
            # Заполняем комбобокс групп
            self.group_combo.clear()
            self.group_combo.addItem("Все компьютеры", None)
            for group in self.groups:
                self.group_combo.addItem(group.get('group_name', 'Без названия'), group.get('group_id'))
                
        except Exception as e:
            print(f"Ошибка загрузки данных для отчетов: {e}")
            self.all_computers = []
            self.groups = []
    
    def get_filtered_computers(self):
        """Возвращает отфильтрованный список компьютеров по выбранной группе"""
        selected_group_id = self.group_combo.currentData()
        
        if selected_group_id is None:
            return self.all_computers
        
        return [c for c in self.all_computers if c.get('group_id') == selected_group_id]
    
    def generate_report(self):
        """Формирует выбранный отчет"""
        self.clear_report_area()
        self._current_figure = None
        
        computers = self.get_filtered_computers()
        report_type = self.report_type.currentText()
        period = self.date_range.get_period()
        
        if not computers:
            self._show_no_data_error("Нет компьютеров для формирования отчета")
            return
        
        # Заголовок отчета
        group_name = self.group_combo.currentText()
        title = QLabel(f"{report_type}\nГруппа: {group_name}\nКомпьютеров в отчете: {len(computers)}\nПериод: {period['from']} — {period['to']}")
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
            self._generate_disk_space_report(computers, period)
        elif "Средние показатели" in report_type:
            self._generate_average_metrics_report(computers, period)
        elif "операционным системам" in report_type:
            self._generate_os_report(computers)
        elif "Отчет по железу" in report_type:
            self._generate_hardware_report(computers, period)
        elif "Время работы" in report_type:
            self._generate_uptime_report(computers, period)
    
    def _get_metrics_for_computer(self, computer_id, period):
        """Получает метрики для компьютера за период"""
        try:
            if not computer_id:
                return None
            
            result = APIClient.get('/metrics/performance', params={
                'computer_id': computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                return data.get('performance', [])
            return None
        except Exception as e:
            print(f"Ошибка загрузки метрик: {e}")
            return None
    
    def _get_average_metrics_for_computer(self, computer_id, period):
        """Получает средние метрики для компьютера за период"""
        try:
            if not computer_id:
                return None
            
            result = APIClient.get('/metrics/average', params={
                'computer_id': computer_id,
                'from': period['from'],
                'to': period['to']
            })
            
            if result and result.get('success'):
                data = result.get('data', {})
                avg_data = data.get('average', {})
                return {
                    'cpu_usage': avg_data.get('cpu_usage'),
                    'ram_usage': avg_data.get('ram_usage'),
                    'disk_usage': avg_data.get('disk_usage'),
                    'network_sent_mb': avg_data.get('network_sent_mb', 0),
                    'network_recv_mb': avg_data.get('network_recv_mb', 0)
                }
            return None
        except Exception as e:
            print(f"Ошибка загрузки средних метрик: {e}")
            return None
    
    def _get_computer_sessions(self, computer_id):
        """Получает список сессий для компьютера"""
        try:
            if not computer_id:
                return []
            
            result = APIClient.get(f'/computers/{computer_id}/sessions')
            if result and result.get('success'):
                data = result.get('data', {})
                return data.get('sessions', [])
            return []
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
            return []
    
    def _get_computer_full_info(self, computer_id):
        """Получает полную информацию о компьютере (включая GPU)"""
        try:
            if not computer_id:
                return {}
            
            result = APIClient.get(f'/computers/{computer_id}')
            if result and result.get('success'):
                return result.get('data', {})
            return {}
        except Exception as e:
            print(f"Ошибка загрузки полной информации о компьютере: {e}")
            return {}
    
    def _calculate_session_duration(self, start_time, end_time=None):
        """Вычисляет длительность сессии в секундах"""
        try:
            if not start_time:
                return 0
            
            # Парсим RFC дату
            start = parsedate_to_datetime(start_time)
            
            if end_time:
                end = parsedate_to_datetime(end_time)
            else:
                end = datetime.now()
            
            delta = end - start
            return max(0, int(delta.total_seconds()))
        except Exception as e:
            print(f"Ошибка расчета длительности: {e}")
            return 0
    
    def _get_total_uptime(self, computer_id):
        """Вычисляет общее время работы компьютера, суммируя все сессии"""
        sessions = self._get_computer_sessions(computer_id)
        total_seconds = 0
        
        for session in sessions:
            start_time = session.get('start_time')
            end_time = session.get('end_time')
            duration = self._calculate_session_duration(start_time, end_time)
            total_seconds += duration
        
        return total_seconds
    
    def _format_uptime(self, seconds):
        """Форматирует время в удобный вид"""
        if seconds <= 0:
            return "—"
        
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        
        if days > 0:
            return f"{days} д {hours} ч"
        elif hours > 0:
            return f"{hours} ч {minutes} м"
        elif minutes > 0:
            return f"{minutes} м"
        else:
            return f"{seconds} с"
    
    def _prepare_disk_data(self, computers, period):
        """Подготавливает данные по дискам для всех компьютеров.
        Возвращает список словарей с ключами: hostname, total, used, free, status_key (0=ok, 1=warn, 2=critical)
        """
        result = []
        for comp in computers:
            hostname = comp.get('hostname', 'Unknown')
            computer_id = comp.get('computer_id')
            
            total = 0.0
            used = None
            
            try:
                metrics = self._get_metrics_for_computer(computer_id, period)
                if metrics and len(metrics) > 0:
                    last_metric = metrics[-1]
                    total = float(last_metric.get('disk_total_gb', 0)) if last_metric.get('disk_total_gb') else 0.0
                    used = float(last_metric.get('disk_used_gb', 0)) if last_metric.get('disk_used_gb') else None
                
                if not total:
                    total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0.0
            except Exception as e:
                print(f"Ошибка загрузки данных диска для {hostname}: {e}")
                total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0.0
            
            total = total or 0.0
            free = total - used if total and used is not None else 0.0
            
            status_key = 0
            if total and used is not None and (total - used) / total < 0.1:
                status_key = 2
            elif total and used is not None and (total - used) / total < 0.2:
                status_key = 1
            
            result.append({
                'hostname': hostname,
                'total': total,
                'used': used,
                'free': free,
                'status_key': status_key
            })
        return result
    
    def _generate_disk_space_report(self, computers, period):
        """Отчет по свободному месту на дисках"""
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            # Таблица отображается сразу, строки заполняются постепенно
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Компьютер", "Всего, ГБ", "Использовано, ГБ", "Свободно, ГБ", "Статус"])
            table.setRowCount(len(computers))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True)
            
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка данных о дисковом пространстве...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            self.report_container_layout.addWidget(table)
            
            for row, comp in enumerate(computers):
                data = self._prepare_disk_data([comp], period)
                d = data[0] if data else {'hostname': comp.get('hostname', 'Unknown'), 'total': 0.0, 'used': None, 'free': 0.0, 'status_key': 0}
                
                status_text = "✅ Нормально"
                if d['status_key'] == 2:
                    status_text = "⚠️ Нужно почистить!"
                elif d['status_key'] == 1:
                    status_text = "⚠️ Мало места"
                
                status_item = QTableWidgetItem(status_text)
                if d['status_key'] == 2:
                    status_item.setBackground(QColor("#e74c3c"))
                    status_item.setForeground(QColor("white"))
                elif d['status_key'] == 1:
                    status_item.setBackground(QColor("#f39c12"))
                else:
                    status_item.setBackground(QColor("#27ae60"))
                
                used_str = f"{d['used']:.1f}" if d['used'] is not None else "—"
                free_str = f"{d['free']:.1f}" if d['total'] and d['used'] is not None else "—"
                
                table.setItem(row, 0, QTableWidgetItem(d['hostname']))
                table.setItem(row, 1, QTableWidgetItem(f"{d['total']:.1f}" if d['total'] else "—"))
                table.setItem(row, 2, QTableWidgetItem(used_str))
                table.setItem(row, 3, QTableWidgetItem(free_str))
                table.setItem(row, 4, status_item)
                
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            # Для графика собираем данные с прогресс-баром, потом строим график
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка данных о дисковом пространстве...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            
            disk_data = []
            for row, comp in enumerate(computers):
                data = self._prepare_disk_data([comp], period)
                if data:
                    disk_data.append(data[0])
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            self._create_disk_space_chart(disk_data)
    
    def _generate_average_metrics_report(self, computers, period):
        """Отчет по средним показателям производительности"""
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            # Таблица отображается сразу, строки заполняются постепенно
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Компьютер", "CPU среднее, %", "RAM среднее, %", "Disk среднее, %", "Network, МБ/с"])
            table.setRowCount(len(computers))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True)
            
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка средних показателей...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            self.report_container_layout.addWidget(table)
            
            for row, comp in enumerate(computers):
                hostname = comp.get('hostname', 'Unknown')
                computer_id = comp.get('computer_id')
                avg_data = self._get_average_metrics_for_computer(computer_id, period)
                
                if avg_data:
                    avg_cpu = avg_data.get('cpu_usage', 0) or 0
                    avg_ram = avg_data.get('ram_usage', 0) or 0
                    avg_disk = avg_data.get('disk_usage', 0) or 0
                    network_total = avg_data.get('network_sent_mb', 0) + avg_data.get('network_recv_mb', 0)
                else:
                    avg_cpu = avg_ram = avg_disk = network_total = 0
                
                table.setItem(row, 0, QTableWidgetItem(hostname))
                table.setItem(row, 1, QTableWidgetItem(f"{avg_cpu:.1f}" if avg_cpu else "—"))
                table.setItem(row, 2, QTableWidgetItem(f"{avg_ram:.1f}" if avg_ram else "—"))
                table.setItem(row, 3, QTableWidgetItem(f"{avg_disk:.1f}" if avg_disk else "—"))
                table.setItem(row, 4, QTableWidgetItem(f"{network_total:.2f}" if network_total else "—"))
                
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка средних показателей...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            
            metrics_data = []
            for row, comp in enumerate(computers):
                hostname = comp.get('hostname', 'Unknown')
                computer_id = comp.get('computer_id')
                avg_data = self._get_average_metrics_for_computer(computer_id, period)
                
                if avg_data:
                    avg_cpu = avg_data.get('cpu_usage', 0) or 0
                    avg_ram = avg_data.get('ram_usage', 0) or 0
                    avg_disk = avg_data.get('disk_usage', 0) or 0
                    network_total = avg_data.get('network_sent_mb', 0) + avg_data.get('network_recv_mb', 0)
                else:
                    avg_cpu = avg_ram = avg_disk = network_total = 0
                
                metrics_data.append({
                    'hostname': hostname,
                    'cpu': avg_cpu,
                    'ram': avg_ram,
                    'disk': avg_disk,
                    'network': network_total
                })
                
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            self._create_average_metrics_chart(metrics_data)
    
    def _generate_os_report(self, computers):
        """Статистика по операционным системам (всегда круговая диаграмма)"""
        os_stats = {}
        for comp in computers:
            os_name = comp.get('os_name', 'Неизвестно')
            if not os_name or os_name == 'Unknown':
                os_name = 'Неизвестно'
            os_stats[os_name] = os_stats.get(os_name, 0) + 1
        
        if MATPLOTLIB_AVAILABLE:
            self._create_os_pie_chart(os_stats)
        else:
            self._show_no_data_error("Matplotlib не установлен. Невозможно отобразить диаграмму.")
    
    def _generate_hardware_report(self, computers, period):
        """Отчет по конфигурациям железа (с данными GPU)"""
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            # Таблица отображается сразу, строки заполняются постепенно
            table = QTableWidget()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"])
            table.setRowCount(len(computers))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True)
            
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка данных о конфигурации компьютеров...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            self.report_container_layout.addWidget(table)
            
            for row, comp in enumerate(computers):
                hostname = comp.get('hostname', 'Unknown')
                computer_id = comp.get('computer_id')
                cpu = comp.get('cpu_model', 'Unknown') or 'Unknown'
                cores = comp.get('cpu_cores', 0)
                ram = float(comp.get('ram_total', 0)) if comp.get('ram_total') else 0.0
                disk = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0.0
                
                # Получаем GPU из полной информации о компьютере
                gpu = "—"
                if computer_id:
                    full_info = self._get_computer_full_info(computer_id)
                    gpu = full_info.get('gpu_model', '')
                    if not gpu or gpu == 'Unknown' or gpu == '':
                        gpu = "—"
                
                table.setItem(row, 0, QTableWidgetItem(hostname))
                table.setItem(row, 1, QTableWidgetItem(cpu))
                table.setItem(row, 2, QTableWidgetItem(str(cores) if cores else "—"))
                table.setItem(row, 3, QTableWidgetItem(f"{ram:.1f}" if ram else "—"))
                table.setItem(row, 4, QTableWidgetItem(gpu))
                table.setItem(row, 5, QTableWidgetItem(f"{disk:.1f}" if disk else "—"))
                
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_label = QLabel("Загрузка данных о конфигурации компьютеров...")
            progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, len(computers))
            progress_bar.setValue(0)
            progress_layout.addWidget(progress_label)
            progress_layout.addWidget(progress_bar)
            self.report_container_layout.addWidget(progress_widget)
            
            hw_data = []
            for row, comp in enumerate(computers):
                hostname = comp.get('hostname', 'Unknown')
                computer_id = comp.get('computer_id')
                cpu = comp.get('cpu_model', 'Unknown') or 'Unknown'
                cores = comp.get('cpu_cores', 0)
                ram = float(comp.get('ram_total', 0)) if comp.get('ram_total') else 0.0
                disk = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0.0
                
                # Получаем GPU из полной информации о компьютере
                gpu = "—"
                if computer_id:
                    full_info = self._get_computer_full_info(computer_id)
                    gpu = full_info.get('gpu_model', '')
                    if not gpu or gpu == 'Unknown' or gpu == '':
                        gpu = "—"
                
                hw_data.append({
                    'hostname': hostname,
                    'cpu': cpu,
                    'cores': cores,
                    'ram': ram,
                    'gpu': gpu,
                    'disk': disk
                })
                
                progress_bar.setValue(row + 1)
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
            
            progress_widget.deleteLater()
            self._create_hardware_chart(hw_data)
    
    def _generate_uptime_report(self, computers, period):
        """Отчет по времени работы компьютеров (общее время из сессий)"""
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Компьютер", "Общее время работы", "Количество сессий"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        # Показываем прогресс-бар загрузки
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_label = QLabel("Загрузка данных о сессиях...")
        progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, len(computers))
        progress_bar.setValue(0)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(progress_bar)
        self.report_container_layout.addWidget(progress_widget)
        self.report_container_layout.addWidget(table)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            computer_id = comp.get('computer_id')
            
            # Получаем сессии и считаем общее время
            sessions = self._get_computer_sessions(computer_id)
            total_seconds = 0
            
            for session in sessions:
                start_time = session.get('start_time')
                end_time = session.get('end_time')
                duration = self._calculate_session_duration(start_time, end_time)
                total_seconds += duration
            
            total_uptime_formatted = self._format_uptime(total_seconds)
            session_count = len(sessions)
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(total_uptime_formatted))
            table.setItem(row, 2, QTableWidgetItem(str(session_count) if session_count else "—"))
            
            # Обновляем прогресс
            progress_bar.setValue(row + 1)
            progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
            QApplication.processEvents()
        
        # Удаляем виджет прогресса
        progress_widget.deleteLater()
    
    # ==================== ГРАФИКИ ====================
    
    def _create_disk_space_chart(self, disk_data):
        """Создает график свободного места"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = []
        free_space = []
        bar_colors = []
        
        for d in disk_data[:20]:
            hostnames.append(d['hostname'][:12])
            free_space.append(d['free'])
            
            if d['status_key'] == 2:
                bar_colors.append('#e74c3c')
            elif d['status_key'] == 1:
                bar_colors.append('#f39c12')
            else:
                bar_colors.append('#27ae60')
        
        figure = Figure(figsize=(10, 5), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        ax.bar(hostnames, free_space, color=bar_colors, edgecolor='white')
        ax.set_title("Свободное место на дисках, ГБ", fontsize=14, fontweight='bold')
        ax.set_ylabel("Свободно, ГБ")
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
        self._current_figure = figure
    
    def _create_average_metrics_chart(self, metrics_data):
        """Создает график средних показателей"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = [d['hostname'][:12] for d in metrics_data[:15]]
        cpu_values = [d['cpu'] for d in metrics_data[:15]]
        ram_values = [d['ram'] for d in metrics_data[:15]]
        
        figure = Figure(figsize=(12, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        x = range(len(hostnames))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], cpu_values, width, label='CPU, %', color='#3498db')
        ax.bar([i + width/2 for i in x], ram_values, width, label='RAM, %', color='#2ecc71')
        
        ax.set_title("Средние показатели CPU и RAM по компьютерам", fontsize=14, fontweight='bold')
        ax.set_ylabel("Процент, %")
        ax.set_xticks(x)
        ax.set_xticklabels(hostnames, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
        self._current_figure = figure
    
    def _create_os_pie_chart(self, os_stats):
        """Круговая диаграмма по ОС"""
        figure = Figure(figsize=(8, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        values = list(os_stats.values())
        labels = list(os_stats.keys())
        pie_colors = ['#3498db', '#2ecc71', '#9b59b6', '#e74c3c', '#f39c12', '#1abc9c']
        
        ax.pie(values, labels=labels, colors=pie_colors[:len(values)],
               autopct='%1.1f%%', startangle=90)
        ax.set_title("Распределение по операционным системам", fontsize=14, fontweight='bold')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
        self._current_figure = figure
    
    def _create_hardware_chart(self, hw_data):
        """Создает график по RAM и дискам"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = [d['hostname'][:12] for d in hw_data[:15]]
        ram_values = [d['ram'] for d in hw_data[:15]]
        disk_values = [d['disk'] for d in hw_data[:15]]
        
        figure = Figure(figsize=(12, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        x = range(len(hostnames))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], ram_values, width, label='RAM, ГБ', color='#9b59b6')
        ax.bar([i + width/2 for i in x], disk_values, width, label='Диск, ГБ', color='#1abc9c')
        
        ax.set_title("Конфигурация RAM и дисков", fontsize=14, fontweight='bold')
        ax.set_ylabel("Объем, ГБ")
        ax.set_xticks(x)
        ax.set_xticklabels(hostnames, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
        self._current_figure = figure
    
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
    
    # ==================== ЭКСПОРТ В PDF ====================
    
    def _save_figure_to_bytes(self, figure):
        """Сохраняет matplotlib фигуру в BytesIO как PNG"""
        buf = BytesIO()
        figure.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        return buf
    
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
        view_type = self.report_view_type.currentText()
        
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
            group_name = self.group_combo.currentText()
            title = Paragraph(f"Общий отчет: {report_type}", title_style)
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            story.append(Paragraph(f"Группа: {group_name}", normal_style))
            story.append(Paragraph(f"Период: {period.get('from', '')} — {period.get('to', '')}", normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            computers = self.get_filtered_computers()
            
            # Проверяем: если есть фигура и выбран вид графика — экспортируем как изображение
            is_chart_view = view_type in ("Гистограмма", "Круговая диаграмма")
            
            if "Свободное место на дисках" in report_type:
                if is_chart_view and self._current_figure:
                    img_buf = self._save_figure_to_bytes(self._current_figure)
                    img = Image(img_buf, width=6*inch, height=3*inch)
                    story.append(Paragraph("Отчет по свободному месту на дисках:", heading_style))
                    story.append(img)
                else:
                    story.append(Paragraph("Отчет по свободному месту на дисках:", heading_style))
                    
                    disk_data = self._prepare_disk_data(computers, period)
                    table_data = [["Компьютер", "Всего, ГБ", "Использовано, ГБ", "Свободно, ГБ", "Статус"]]
                    for d in disk_data[:50]:
                        status = "Нормально"
                        if d['status_key'] == 2:
                            status = "Нужно почистить!"
                        elif d['status_key'] == 1:
                            status = "Мало места"
                        
                        used_str = f"{d['used']:.1f}" if d['used'] is not None else "—"
                        free_str = f"{d['free']:.1f}" if d['total'] and d['used'] is not None else "—"
                        
                        table_data.append([
                            d['hostname'],
                            f"{d['total']:.1f}" if d['total'] else "—",
                            used_str,
                            free_str,
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
            
            elif "Средние показатели" in report_type:
                if is_chart_view and self._current_figure:
                    img_buf = self._save_figure_to_bytes(self._current_figure)
                    img = Image(img_buf, width=6*inch, height=3*inch)
                    story.append(Paragraph("Отчет по средним показателям производительности:", heading_style))
                    story.append(img)
                else:
                    story.append(Paragraph("Отчет по средним показателям производительности:", heading_style))
                    
                    table_data = [["Компьютер", "CPU среднее, %", "RAM среднее, %", "Disk среднее, %", "Network, МБ/с"]]
                    for comp in computers[:50]:
                        hostname = comp.get('hostname', 'Unknown')
                        computer_id = comp.get('computer_id')
                        
                        avg_data = self._get_average_metrics_for_computer(computer_id, period)
                        
                        if avg_data:
                            avg_cpu = f"{avg_data.get('cpu_usage', 0):.1f}" if avg_data.get('cpu_usage') else "—"
                            avg_ram = f"{avg_data.get('ram_usage', 0):.1f}" if avg_data.get('ram_usage') else "—"
                            avg_disk = f"{avg_data.get('disk_usage', 0):.1f}" if avg_data.get('disk_usage') else "—"
                            network_total = avg_data.get('network_sent_mb', 0) + avg_data.get('network_recv_mb', 0)
                            network_str = f"{network_total:.2f}" if network_total else "—"
                        else:
                            avg_cpu = avg_ram = avg_disk = network_str = "—"
                        
                        table_data.append([hostname, avg_cpu, avg_ram, avg_disk, network_str])
                    
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
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ]))
                    story.append(table)
            
            elif "операционным системам" in report_type:
                # Всегда экспортируем круговую диаграмму
                if self._current_figure:
                    img_buf = self._save_figure_to_bytes(self._current_figure)
                    img = Image(img_buf, width=5*inch, height=3.75*inch)
                    story.append(Paragraph("Статистика по операционным системам:", heading_style))
                    story.append(img)
                else:
                    # Fallback: генерируем таблицу если нет фигуры
                    os_stats = {}
                    for comp in computers:
                        os_name = comp.get('os_name', 'Неизвестно')
                        if not os_name or os_name == 'Unknown':
                            os_name = 'Неизвестно'
                        os_stats[os_name] = os_stats.get(os_name, 0) + 1
                    
                    table_data = [["Операционная система", "Количество компьютеров"]]
                    for os_name, count in os_stats.items():
                        table_data.append([os_name, str(count)])
                    
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
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ]))
                    story.append(table)
            
            elif "Отчет по железу" in report_type:
                if is_chart_view and self._current_figure:
                    img_buf = self._save_figure_to_bytes(self._current_figure)
                    img = Image(img_buf, width=6*inch, height=3*inch)
                    story.append(Paragraph("Отчет по конфигурации железа:", heading_style))
                    story.append(img)
                else:
                    story.append(Paragraph("Отчет по конфигурации железа:", heading_style))
                    
                    table_data = [["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"]]
                    for comp in computers[:50]:
                        hostname = comp.get('hostname', 'Unknown')
                        computer_id = comp.get('computer_id')
                        cpu = comp.get('cpu_model', 'Unknown') or 'Unknown'
                        cores = comp.get('cpu_cores', 0)
                        ram_val = comp.get('ram_total', 0)
                        disk_val = comp.get('storage_total', 0)
                        # Безопасное приведение к float для форматирования
                        try:
                            ram_f = float(ram_val) if ram_val else 0.0
                        except (ValueError, TypeError):
                            ram_f = 0.0
                        try:
                            disk_f = float(disk_val) if disk_val else 0.0
                        except (ValueError, TypeError):
                            disk_f = 0.0
                        
                        # Получаем GPU
                        gpu = "—"
                        if computer_id:
                            full_info = self._get_computer_full_info(computer_id)
                            gpu = full_info.get('gpu_model', '')
                            if not gpu or gpu == 'Unknown':
                                gpu = "—"
                        
                        ram_str = f"{ram_f:.1f}" if ram_f else "—"
                        disk_str = f"{disk_f:.1f}" if disk_f else "—"
                        
                        table_data.append([
                            hostname,
                            cpu,
                            str(cores) if cores else "—",
                            ram_str,
                            gpu,
                            disk_str
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
            
            elif "Время работы" in report_type:
                story.append(Paragraph("Отчет по времени работы компьютеров:", heading_style))
                
                table_data = [["Компьютер", "Общее время работы", "Количество сессий"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    computer_id = comp.get('computer_id')
                    
                    # Считаем общее время работы через сессии
                    sessions = self._get_computer_sessions(computer_id)
                    total_seconds = 0
                    
                    for session in sessions:
                        start_time = session.get('start_time')
                        end_time = session.get('end_time')
                        duration = self._calculate_session_duration(start_time, end_time)
                        total_seconds += duration
                    
                    total_uptime_formatted = self._format_uptime(total_seconds)
                    session_count = len(sessions)
                    
                    table_data.append([
                        hostname,
                        total_uptime_formatted,
                        str(session_count) if session_count else "—"
                    ])
                
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1abc9c')),
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