"""Вкладка "Общая информация" о компьютере"""

from qtpy.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel, 
                            QFrame, QGroupBox, QScrollArea, QHBoxLayout)
from qtpy.QtCore import Qt

from .widgets import DiskSpaceWidget


class OverviewTab(QWidget):
    """Вкладка с общей информацией о компьютере"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.computer_info_text = None
        self.disk_widget = None
        self.summary_cards = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Группа характеристик компьютера (3 колонки)
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
        
        # Создаем контейнер для 3 колонок
        self.computer_info_text = QLabel()
        self.computer_info_text.setWordWrap(True)
        self.computer_info_text.setStyleSheet("padding: 10px; font-size: 13px;")
        info_layout.addWidget(self.computer_info_text)
        
        scroll_layout.addWidget(info_group)
        
        # Группа состояния диска
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
        
        # Группа сводки за период
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
            card = self._create_summary_card(title, value, color)
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
    
    def _create_summary_card(self, title, value, color):
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
    
    def update_computer_info(self, data, current_disk_info):
        """Обновляет отображение информации о компьютере (3 колонки)"""
        hostname = data.get('hostname', 'Unknown')
        ip_address = data.get('current_ip', 'Unknown')
        user_login = data.get('login', 'Не назначен')
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
        group_name = data.get('group_name', '—')
        inventory_number = data.get('inventory_number', '—')
        
        if last_online and isinstance(last_online, str):
            last_online = last_online[:19]
        if created_at and isinstance(created_at, str):
            created_at = created_at[:19]
        
        user_display = f"{user_login}" + (f" ({full_name})" if full_name else "")
        
        # Разделяем характеристики на две колонки
        left_col = [
            ("IP адрес:", ip_address),
            ("Пользователь:", user_display),
            ("MAC адрес:", mac_address),
            ("Тип:", computer_type),
            ("Группа:", group_name),
            ("Инв. номер:", inventory_number),
        ]
        
        right_col = [
            ("ОС:", f"{os_name} {os_version} {os_architecture}".strip()),
            ("CPU:", f"{cpu_model} ({cpu_cores} ядер)"),
            ("RAM:", f"{ram_total} GB"),
            ("Диск:", f"{storage_total} GB"),
            ("GPU:", gpu_model),
            ("Материнская плата:", motherboard),
            ("BIOS версия:", bios_version),
        ]
        
        # Формируем HTML с 3 колонками
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr>'
        
        # Колонка 1
        html += '<td style="padding: 8px; width: 30%; vertical-align: top;">'
        html += '<table style="width: 100%;">'
        for label, value in left_col:
            html += f'<tr><td style="padding: 4px;"><b>{label}</b></td><td style="padding: 4px;">{value}</td></tr>'
        html += '</table>'
        html += '</td>'
        
        # Колонка 2
        html += '<td style="padding: 8px; width: 30%; vertical-align: top;">'
        html += '<table style="width: 100%;">'
        for label, value in right_col:
            html += f'<tr><td style="padding: 4px;"><b>{label}</b></td><td style="padding: 4px;">{value}</td></tr>'
        html += '</table>'
        html += '</td>'
        
        # Колонка 3 - Описание
        html += '<td style="padding: 8px; width: 40%; vertical-align: top;">'
        html += f'<b>Описание:</b><br><br>{description}<br><br>'
        html += f'<b>Создан:</b><br>{created_at}<br><br>'
        html += f'<b>Последний вход:</b><br>{last_online}'
        html += '</td>'
        
        html += '</tr>'
        html += '</table>'
        
        self.computer_info_text.setText(html)
        
        # Обновляем виджет диска
        self.disk_widget.update_disk_info(
            current_disk_info.get('used_gb'),
            current_disk_info.get('total_gb')
        )
    
    def update_summary(self, key, value):
        """Обновляет значение в карточке сводки"""
        if key in self.summary_cards:
            if isinstance(value, float):
                display = f"{value:.1f}%" if '%' in key.lower() or 'cpu' in key.lower() or 'ram' in key.lower() or 'disk' in key.lower() else f"{value:.0f}"
            else:
                display = str(value)
            self.summary_cards[key].value_label.setText(display)