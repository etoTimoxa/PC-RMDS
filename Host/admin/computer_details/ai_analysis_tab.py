"""Вкладка "AI Анализ" - анализ состояния компьютера с помощью ИИ"""

import requests
from datetime import datetime
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QFrame, QProgressBar, QScrollArea, QSplitter,
    QMessageBox
)
from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtGui import QFont

from utils.constants import LLM_CONFIG


class AIAnalysisThread(QThread):
    """Поток для выполнения запроса к LLM"""
    started_analysis = Signal()
    finished_analysis = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, computer_data, metrics, events, anomalies, session_info, period):
        super().__init__()
        self.computer_data = computer_data
        self.metrics = metrics
        self.events = events
        self.anomalies = anomalies
        self.session_info = session_info
        self.period = period
    
    def run(self):
        try:
            # Формируем промпт для нейросети
            prompt = self._build_prompt()
            
            url = f"{LLM_CONFIG['base_url']}/chat/completions"
            headers = {
                "Authorization": f"Bearer {LLM_CONFIG['api_key']}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": LLM_CONFIG["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": """Ты — эксперт по системному администрированию и анализу 
производительности компьютеров. Твоя задача — анализировать предоставленные 
метрики и давать полезные рекомендации.

Формат ответа должен быть строго следующим:

## 📊 ОБЩАЯ ОЦЕНКА СОСТОЯНИЯ
(краткая оценка отлично/хорошо/удовлетворительно/критично)

## 🔍 ДЕТАЛЬНЫЙ АНАЛИЗ
- CPU: (анализ загрузки процессора)
- RAM: (анализ использования памяти)
- Disk: (анализ дисковой подсистемы)
- Network: (анализ сетевой активности)

## ⚠️ ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ И АНОМАЛИИ
(список проблем с приоритетом: КРИТИЧНО, ВАЖНО, РЕКОМЕНДУЕТСЯ)

## 💡 РЕКОМЕНДАЦИИ ПО УСТРАНЕНИЮ
(конкретные действия для решения каждой проблемы)

## 📈 ТРЕНДЫ И ПРОГНОЗЫ
(анализ динамики метрик и прогноз на ближайшее время)

## ✅ ИТОГОВЫЙ ЧЕК-ЛИСТ
(короткий список главных действий)

Будь конкретным, используй цифры из метрик. Давай практические советы."""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                self.finished_analysis.emit(result)
            else:
                self.error_occurred.emit(f"Ошибка API: {response.status_code}\n{response.text}")
                
        except requests.exceptions.Timeout:
            self.error_occurred.emit("Превышено время ожидания ответа от сервера")
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Ошибка подключения к серверу LLM")
        except Exception as e:
            self.error_occurred.emit(f"Ошибка: {str(e)}")
    
    def _build_prompt(self):
        """Формирует промпт с данными о компьютере"""
        
        # Базовая информация о компьютере
        computer_info = f"""
=== ИНФОРМАЦИЯ О КОМПЬЮТЕРЕ ===
Hostname: {self.computer_data.get('hostname', 'Unknown')}
ОС: {self.computer_data.get('os_name', 'Unknown')} {self.computer_data.get('os_version', '')}
CPU: {self.computer_data.get('cpu_model', 'Unknown')} ({self.computer_data.get('cpu_cores', '?')} ядер)
RAM: {self.computer_data.get('ram_total', '?')} GB
Диск: {self.computer_data.get('storage_total', '?')} GB
Тип: {self.computer_data.get('computer_type', 'client')}
Группа: {self.computer_data.get('group_name', '—')}
Инв. номер: {self.computer_data.get('inventory_number', '—')}
Статус: {"В сети" if self.computer_data.get('is_online') else "Не в сети"}
"""
        
        # Метрики производительности
        metrics_info = "\n=== МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ ===\n"
        if self.metrics:
            # Расчет средних значений
            cpu_values = [m.get('cpu_usage', 0) for m in self.metrics if m.get('cpu_usage')]
            ram_values = [m.get('ram_usage', 0) for m in self.metrics if m.get('ram_usage')]
            disk_values = [m.get('disk_usage', 0) for m in self.metrics if m.get('disk_usage')]
            
            if cpu_values:
                metrics_info += f"Средний CPU: {sum(cpu_values)/len(cpu_values):.1f}%\n"
                metrics_info += f"Макс CPU: {max(cpu_values):.1f}%\n"
                metrics_info += f"Мин CPU: {min(cpu_values):.1f}%\n"
            
            if ram_values:
                metrics_info += f"Средняя RAM: {sum(ram_values)/len(ram_values):.1f}%\n"
                metrics_info += f"Макс RAM: {max(ram_values):.1f}%\n"
            
            if disk_values:
                metrics_info += f"Средний Disk: {sum(disk_values)/len(disk_values):.1f}%\n"
            
            # Последние метрики
            last = self.metrics[-1] if self.metrics else {}
            metrics_info += f"\n--- ПОСЛЕДНИЕ ЗНАЧЕНИЯ ---\n"
            metrics_info += f"CPU: {last.get('cpu_usage', '—')}%\n"
            metrics_info += f"RAM: {last.get('ram_usage', '—')}% ({last.get('ram_used_gb', '—')} GB из {last.get('ram_total_gb', '—')} GB)\n"
            metrics_info += f"Disk: {last.get('disk_usage', '—')}%\n"
            metrics_info += f"Network отправлено: {last.get('network_sent_mb', 0):.2f} MB\n"
            metrics_info += f"Network получено: {last.get('network_recv_mb', 0):.2f} MB\n"
        
        # События и ошибки
        events_info = "\n=== СОБЫТИЯ И ОШИБКИ ===\n"
        if self.events:
            # Группируем по типам
            event_counts = {}
            error_events = []
            
            for event in self.events:
                event_type = event.get('type', 'unknown')
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                
                # Собираем ошибки Windows
                if event_type == 'windows_event' or event_type == 'system_error':
                    data = event.get('data', {})
                    msg = data.get('message', '') or data.get('description', '')
                    if msg:
                        error_events.append(f"  - {msg[:200]}")
            
            events_info += f"Всего событий: {len(self.events)}\n"
            events_info += "Распределение по типам:\n"
            for ev_type, count in sorted(event_counts.items(), key=lambda x: x[1], reverse=True):
                events_info += f"  - {ev_type}: {count}\n"
            
            if error_events:
                events_info += f"\nОШИБКИ (первые 10):\n"
                for err in error_events[:10]:
                    events_info += f"{err}\n"
        else:
            events_info += "Событий за период не обнаружено\n"
        
        # Аномалии
        anomalies_info = "\n=== АНОМАЛИИ ===\n"
        if self.anomalies:
            anomalies_info += f"Обнаружено аномалий: {len(self.anomalies)}\n"
            anomalies_info += "Детали аномалий:\n"
            for anomaly in self.anomalies[:20]:  # Ограничиваем 20
                timestamp = anomaly.get('timestamp', '')[:19]
                cpu = anomaly.get('cpu_usage', '—')
                ram = anomaly.get('ram_usage', '—')
                anomalies_info += f"  - {timestamp}: CPU={cpu}%, RAM={ram}%\n"
        else:
            anomalies_info += "Аномалий не обнаружено\n"
        
        # Информация о сессиях
        sessions_info = "\n=== СЕССИИ ===\n"
        if self.session_info:
            active = [s for s in self.session_info if s.get('status_name') == 'active']
            closed = [s for s in self.session_info if s.get('status_name') != 'active']
            sessions_info += f"Активных сессий: {len(active)}\n"
            sessions_info += f"Завершенных сессий: {len(closed)}\n"
        
        # Период анализа
        period_info = f"\n=== ПЕРИОД АНАЛИЗА ===\n"
        period_info += f"С: {self.period.get('from', '—')}\n"
        period_info += f"По: {self.period.get('to', '—')}\n"
        
        # Итоговый промпт
        full_prompt = f"""
Пожалуйста, проанализируй состояние компьютера на основе следующих данных:

{computer_info}
{metrics_info}
{events_info}
{anomalies_info}
{sessions_info}
{period_info}

Дай развернутый анализ и конкретные рекомендации по улучшению работы системы.
"""
        return full_prompt


class AIAnalysisTab(QWidget):
    """Вкладка с AI-анализом состояния компьютера"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.analysis_thread = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Верхняя панель с кнопкой
        top_panel = QHBoxLayout()
        
        self.analyze_btn = QPushButton("🔍 Запустить AI-анализ")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.setMinimumWidth(200)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #9b59b6;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.analyze_btn.clicked.connect(self.start_analysis)
        top_panel.addWidget(self.analyze_btn)
        
        self.status_label = QLabel("Готов к анализу")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        top_panel.addWidget(self.status_label)
        
        top_panel.addStretch()
        layout.addLayout(top_panel)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Бесконечный прогресс
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                height: 5px;
            }
            QProgressBar::chunk {
                background-color: #8e44ad;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Основная область с результатами
        self.result_area = QScrollArea()
        self.result_area.setWidgetResizable(True)
        self.result_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                background-color: #fafafa;
            }
        """)
        
        self.result_widget = QWidget()
        self.result_layout = QVBoxLayout(self.result_widget)
        self.result_layout.setSpacing(15)
        
        # Приветственное сообщение
        welcome_label = QLabel("👋 Нажмите «Запустить AI-анализ» для получения рекомендаций")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("""
            font-size: 16px;
            color: #7f8c8d;
            padding: 50px;
        """)
        self.result_layout.addWidget(welcome_label)
        
        self.result_area.setWidget(self.result_widget)
        layout.addWidget(self.result_area)
    
    def start_analysis(self):
        """Запускает анализ через LLM"""
        if not self.parent_window or not self.parent_window.computer_id:
            QMessageBox.warning(self, "Ошибка", "ID компьютера не определен")
            return
        
        # Проверяем наличие данных
        metrics = self.parent_window.metrics_tab.get_current_metrics()
        events = self.parent_window.events_tab.get_all_events()
        anomalies = self.parent_window.anomalies_tab.anomalies
        sessions = self.parent_window.sessions_tab.get_sessions()
        
        if not metrics and not events and not anomalies:
            reply = QMessageBox.question(
                self,
                "Нет данных",
                "За выбранный период нет данных для анализа.\n"
                "Продолжить анализ с имеющимися данными?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Блокируем кнопку и показываем прогресс
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("⏳ Анализирую...")
        self.progress_bar.setVisible(True)
        self.status_label.setText("Отправка данных на анализ...")
        self.status_label.setStyleSheet("color: #8e44ad; font-size: 12px;")
        
        # Очищаем область результатов
        self._clear_result_area()
        
        # Запускаем поток анализа
        period = self.parent_window.date_range.get_period()
        computer_data = self.parent_window.current_data or {}
        
        self.analysis_thread = AIAnalysisThread(
            computer_data=computer_data,
            metrics=metrics,
            events=events,
            anomalies=anomalies,
            session_info=sessions,
            period=period
        )
        
        self.analysis_thread.started_analysis.connect(self._on_analysis_started)
        self.analysis_thread.finished_analysis.connect(self._on_analysis_finished)
        self.analysis_thread.error_occurred.connect(self._on_analysis_error)
        
        self.analysis_thread.start()
    
    def _clear_result_area(self):
        """Очищает область результатов"""
        while self.result_layout.count():
            child = self.result_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _on_analysis_started(self):
        self.status_label.setText("Анализ данных...")
    
    def _on_analysis_finished(self, result):
        """Отображает результат анализа"""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍 Запустить AI-анализ")
        self.status_label.setText("Анализ завершен")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        
        # Парсим и отображаем результат
        self._display_analysis_result(result)
    
    def _on_analysis_error(self, error_msg):
        """Обрабатывает ошибку анализа"""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🔍 Запустить AI-анализ")
        self.status_label.setText("Ошибка анализа")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        
        # Отображаем ошибку
        error_frame = QFrame()
        error_frame.setStyleSheet("""
            QFrame {
                background-color: #fee;
                border: 1px solid #e74c3c;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        error_layout = QVBoxLayout(error_frame)
        
        error_title = QLabel("❌ Ошибка при выполнении анализа")
        error_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e74c3c;")
        error_layout.addWidget(error_title)
        
        error_text = QLabel(error_msg)
        error_text.setWordWrap(True)
        error_text.setStyleSheet("color: #c0392b;")
        error_layout.addWidget(error_text)
        
        hint_label = QLabel(
            "Возможные причины:\n"
            "• Не настроен LLM сервер в utils/constants.py\n"
            "• Нет подключения к интернету\n"
            "• Превышен таймаут ожидания ответа"
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px; margin-top: 10px;")
        error_layout.addWidget(hint_label)
        
        self.result_layout.addWidget(error_frame)
    
    def _display_analysis_result(self, result):
        """Отображает результат анализа в отформатированном виде"""
        
        # Создаем контейнер для результата
        main_frame = QFrame()
        main_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        main_layout = QVBoxLayout(main_frame)
        
        # Заголовок с датой
        header_label = QLabel(f"📋 AI-Анализ • {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        header_label.setStyleSheet("font-size: 14px; color: #7f8c8d; border-bottom: 1px solid #ecf0f1; padding-bottom: 10px;")
        main_layout.addWidget(header_label)
        
        # Парсим markdown и конвертируем в HTML
        html_content = self._markdown_to_html(result)
        
        # Отображаем результат в QTextEdit
        text_edit = QTextEdit()
        text_edit.setHtml(html_content)
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("""
            QTextEdit {
                border: none;
                background-color: white;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        
        # Настраиваем шрифты
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        text_edit.setFont(font)
        
        main_layout.addWidget(text_edit)
        
        # Кнопка копирования
        copy_btn = QPushButton("📋 Копировать анализ")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2c3e50;
            }
        """)
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(result))
        main_layout.addWidget(copy_btn)
        
        self.result_layout.addWidget(main_frame)
    
    def _markdown_to_html(self, text):
        """Конвертирует markdown в HTML для отображения"""
        import re
        
        # Заменяем заголовки
        text = re.sub(r'^## (.*?)$', r'<h2 style="color: #8e44ad; margin-top: 20px; margin-bottom: 10px; border-left: 4px solid #8e44ad; padding-left: 10px;">\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*?)$', r'<h3 style="color: #2c3e50; margin-top: 15px; margin-bottom: 8px;">\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.MULTILINE)
        
        # Заменяем списки
        text = re.sub(r'^- (.*?)$', r'<li style="margin-left: 20px;">\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^\* (.*?)$', r'<li style="margin-left: 20px;">\1</li>', text, flags=re.MULTILINE)
        
        # Оборачиваем списки в ul
        text = re.sub(r'(<li.*?</li>\n)+', r'<ul style="margin: 5px 0;">\g<0></ul>', text, flags=re.DOTALL)
        
        # Заменяем чек-листы
        text = re.sub(r'^- \[ \] (.*?)$', r'<li style="margin-left: 20px; list-style-type: circle;">☐ \1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^- \[x\] (.*?)$', r'<li style="margin-left: 20px; list-style-type: circle;">☑ \1</li>', text, flags=re.MULTILINE)
        
        # Заменяем эмодзи в заголовках
        emoji_map = {
            '📊': '<span style="font-size: 1.2em;">📊</span>',
            '🔍': '<span style="font-size: 1.2em;">🔍</span>',
            '⚠️': '<span style="font-size: 1.2em;">⚠️</span>',
            '💡': '<span style="font-size: 1.2em;">💡</span>',
            '📈': '<span style="font-size: 1.2em;">📈</span>',
            '✅': '<span style="font-size: 1.2em;">✅</span>',
        }
        for emoji, html_emoji in emoji_map.items():
            text = text.replace(emoji, html_emoji)
        
        # Заменяем переносы строк
        text = text.replace('\n', '<br>')
        
        # Добавляем базовые стили
        html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 0; }}
            h2 {{ color: #8e44ad; margin-top: 20px; margin-bottom: 10px; }}
            h3 {{ color: #2c3e50; margin-top: 15px; margin-bottom: 8px; }}
            ul {{ margin: 5px 0; }}
            li {{ margin-left: 20px; margin-bottom: 5px; }}
            b {{ color: #e74c3c; }}
        </style>
        </head>
        <body>
        {text}
        </body>
        </html>
        """
        return html
    
    def _copy_to_clipboard(self, text):
        """Копирует текст в буфер обмена"""
        from qtpy.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Показываем временное уведомление
        self.status_label.setText("Анализ скопирован в буфер обмена")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        
        # Возвращаем статус через 2 секунды
        from qtpy.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.status_label.setText("Готов к анализу") if self.status_label.text() == "Анализ скопирован в буфер обмена" else None)