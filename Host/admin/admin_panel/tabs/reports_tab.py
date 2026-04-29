"""Вкладка "Отчеты" - общие отчеты по всем компьютерам"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
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
            
        elif "Статус онлайн" in report_type:
            items = ["Таблица"]
            if MATPLOTLIB_AVAILABLE:
                items.append("Круговая диаграмма")
            self.report_view_type.addItems(items)
            
        elif "операционным системам" in report_type:
            items = ["Таблица"]
            if MATPLOTLIB_AVAILABLE:
                items.append("Круговая диаграмма")
            self.report_view_type.addItems(items)
            
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
        elif "Статус онлайн" in report_type:
            self._generate_online_status_report(computers)
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
    
    def _generate_disk_space_report(self, computers, period):
        """Отчет по свободному месту на дисках"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Компьютер", "Всего, ГБ", "Использовано, ГБ", "Свободно, ГБ", "Статус"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            computer_id = comp.get('computer_id')
            
            total = 0
            used = None
            
            try:
                # Пробуем получить из метрик
                metrics = self._get_metrics_for_computer(computer_id, period)
                if metrics and len(metrics) > 0:
                    last_metric = metrics[-1]
                    total = float(last_metric.get('disk_total_gb', 0)) if last_metric.get('disk_total_gb') else 0
                    used = float(last_metric.get('disk_used_gb', 0)) if last_metric.get('disk_used_gb') else None
                
                # Если нет данных из метрик - берем статичные
                if not total:
                    total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
                
            except Exception as e:
                print(f"Ошибка загрузки данных диска для {hostname}: {e}")
                total = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
            
            free = total - used if total and used is not None else 0
            
            # Определяем статус
            status = "✅ Нормально"
            if total and used is not None and free / total < 0.1:
                status = "⚠️ Нужно почистить!"
            elif total and used is not None and free / total < 0.2:
                status = "⚠️ Мало места"
            
            status_item = QTableWidgetItem(status)
            if "Нужно почистить" in status:
                status_item.setBackground(QColor("#e74c3c"))
                status_item.setForeground(QColor("white"))
            elif "Мало места" in status:
                status_item.setBackground(QColor("#f39c12"))
            else:
                status_item.setBackground(QColor("#27ae60"))
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, QTableWidgetItem(f"{total:.1f}" if total else "—"))
            table.setItem(row, 2, QTableWidgetItem(f"{used:.1f}" if used is not None and used else "—"))
            table.setItem(row, 3, QTableWidgetItem(f"{free:.1f}" if total and used is not None else "—"))
            table.setItem(row, 4, status_item)
        
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            self.report_container_layout.addWidget(table)
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            self._create_disk_space_chart(computers)
    
    def _generate_average_metrics_report(self, computers, period):
        """Отчет по средним показателям производительности"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Компьютер", "CPU среднее, %", "RAM среднее, %", "Disk среднее, %", "Network, МБ/с"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
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
        
        view_type = self.report_view_type.currentText()
        if view_type == "Таблица":
            self.report_container_layout.addWidget(table)
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            self._create_average_metrics_chart(computers, period)
    
    def _generate_online_status_report(self, computers):
        """Отчет по статусу онлайн/оффлайн"""
        online = sum(1 for c in computers if c.get('is_online', False))
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
            is_online = comp.get('is_online', False)
            last_online = comp.get('last_online', 'Никогда')
            user = comp.get('login', 'Не назначен')
            full_name = comp.get('full_name', '')
            
            user_display = f"{user}" + (f" ({full_name})" if full_name else "")
            
            status_text = "✅ Онлайн" if is_online else "❌ Оффлайн"
            
            status_item = QTableWidgetItem(status_text)
            if is_online:
                status_item.setForeground(QColor("#27ae60"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            
            table.setItem(row, 0, QTableWidgetItem(hostname))
            table.setItem(row, 1, status_item)
            table.setItem(row, 2, QTableWidgetItem(str(last_online)[:19] if last_online and last_online != 'Никогда' else "Никогда"))
            table.setItem(row, 3, QTableWidgetItem(user_display))
        
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            self.report_container_layout.addWidget(table)
        elif view_type == "Круговая диаграмма" and MATPLOTLIB_AVAILABLE:
            self._create_online_pie_chart(online, offline)
    
    def _generate_os_report(self, computers):
        """Статистика по операционным системам"""
        os_stats = {}
        for comp in computers:
            os_name = comp.get('os_name', 'Неизвестно')
            if not os_name or os_name == 'Unknown':
                os_name = 'Неизвестно'
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
        
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            self.report_container_layout.addWidget(table)
        elif view_type == "Круговая диаграмма" and MATPLOTLIB_AVAILABLE:
            self._create_os_pie_chart(os_stats)
    
    def _generate_hardware_report(self, computers, period):
        """Отчет по конфигурациям железа (с данными GPU)"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"])
        table.setRowCount(len(computers))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        
        # Сначала показываем прогресс
        progress_label = QLabel("Загрузка данных о конфигурации компьютеров...")
        progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(progress_label)
        self.report_container_layout.addWidget(table)
        
        for row, comp in enumerate(computers):
            hostname = comp.get('hostname', 'Unknown')
            computer_id = comp.get('computer_id')
            cpu = comp.get('cpu_model', 'Unknown')
            cores = comp.get('cpu_cores', 0)
            ram = float(comp.get('ram_total', 0)) if comp.get('ram_total') else 0
            disk = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
            
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
            
            # Обновляем прогресс для длинных списков
            if (row + 1) % 10 == 0:
                progress_label.setText(f"Загрузка... {row + 1}/{len(computers)}")
                QApplication.processEvents()
        
        # Удаляем прогресс-лейбл
        progress_label.deleteLater()
        
        view_type = self.report_view_type.currentText()
        
        if view_type == "Таблица":
            pass  # Таблица уже добавлена
        elif view_type == "Гистограмма" and MATPLOTLIB_AVAILABLE:
            self._create_hardware_chart(computers)
    
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
        ax.set_ylabel("Свободно, ГБ")
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
        
        figure.tight_layout()
        canvas.draw()
        self.report_container_layout.addWidget(canvas)
    
    def _create_average_metrics_chart(self, computers, period):
        """Создает график средних показателей"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = []
        cpu_values = []
        ram_values = []
        
        for comp in computers[:15]:  # Ограничиваем 15 компов
            hostname = comp.get('hostname', 'Unknown')[:12]
            computer_id = comp.get('computer_id')
            
            avg_data = self._get_average_metrics_for_computer(computer_id, period)
            
            if avg_data:
                cpu = avg_data.get('cpu_usage', 0) or 0
                ram = avg_data.get('ram_usage', 0) or 0
            else:
                cpu = ram = 0
            
            hostnames.append(hostname)
            cpu_values.append(cpu)
            ram_values.append(ram)
        
        figure = Figure(figsize=(12, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        x = range(len(hostnames))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], cpu_values, width, label='CPU, %', color='#3498db')
        bars2 = ax.bar([i + width/2 for i in x], ram_values, width, label='RAM, %', color='#2ecc71')
        
        ax.set_title("Средние показатели CPU и RAM по компьютерам", fontsize=14, fontweight='bold')
        ax.set_ylabel("Процент, %")
        ax.set_xticks(x)
        ax.set_xticklabels(hostnames, rotation=45, ha='right')
        ax.legend()
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
    
    def _create_hardware_chart(self, computers):
        """Создает график по RAM и дискам"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        hostnames = []
        ram_values = []
        disk_values = []
        
        for comp in computers[:15]:  # Ограничиваем 15 компов
            hostname = comp.get('hostname', 'Unknown')[:12]
            ram = float(comp.get('ram_total', 0)) if comp.get('ram_total') else 0
            disk = float(comp.get('storage_total', 0)) if comp.get('storage_total') else 0
            
            hostnames.append(hostname)
            ram_values.append(ram)
            disk_values.append(disk)
        
        figure = Figure(figsize=(12, 6), facecolor='white')
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)
        
        x = range(len(hostnames))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], ram_values, width, label='RAM, ГБ', color='#9b59b6')
        bars2 = ax.bar([i + width/2 for i in x], disk_values, width, label='Диск, ГБ', color='#1abc9c')
        
        ax.set_title("Конфигурация RAM и дисков", fontsize=14, fontweight='bold')
        ax.set_ylabel("Объем, ГБ")
        ax.set_xticks(x)
        ax.set_xticklabels(hostnames, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
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
            group_name = self.group_combo.currentText()
            title = Paragraph(f"Общий отчет: {report_type}", title_style)
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            story.append(Paragraph(f"Группа: {group_name}", normal_style))
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
                    
                    status = "Нормально"
                    if total and free / total < 0.1:
                        status = "Нужно почистить!"
                    elif total and free / total < 0.2:
                        status = "Мало места"
                    
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
            
            elif "Средние показатели" in report_type:
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
            
            elif "Статус онлайн" in report_type:
                online = sum(1 for c in computers if c.get('is_online', False))
                offline = len(computers) - online
                
                story.append(Paragraph(f"Онлайн: {online} | Оффлайн: {offline}", normal_style))
                story.append(Spacer(1, 0.2*inch))
                
                table_data = [["Компьютер", "Статус", "Последний онлайн", "Пользователь"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    is_online = comp.get('is_online', False)
                    last_online = comp.get('last_online', 'Никогда')
                    user = comp.get('login', 'Не назначен')
                    
                    status_text = "Онлайн" if is_online else "Оффлайн"
                    table_data.append([
                        hostname,
                        status_text,
                        str(last_online)[:19] if last_online and last_online != 'Никогда' else "Никогда",
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
                story.append(Paragraph("Отчет по конфигурации железа:", heading_style))
                
                table_data = [["Компьютер", "CPU", "Ядра", "RAM, ГБ", "GPU", "Диск, ГБ"]]
                for comp in computers[:50]:
                    hostname = comp.get('hostname', 'Unknown')
                    computer_id = comp.get('computer_id')
                    cpu = comp.get('cpu_model', 'Unknown')
                    cores = comp.get('cpu_cores', 0)
                    ram = comp.get('ram_total', 0)
                    disk = comp.get('storage_total', 0)
                    
                    # Получаем GPU
                    gpu = "—"
                    if computer_id:
                        full_info = self._get_computer_full_info(computer_id)
                        gpu = full_info.get('gpu_model', '')
                        if not gpu or gpu == 'Unknown':
                            gpu = "—"
                    
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