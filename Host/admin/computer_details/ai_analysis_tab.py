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
        """Формирует компактный промпт только из критичных данных"""
        
        # 1. Базовая информация о компьютере
        computer_info = f"""Хост: {self.computer_data.get('hostname', 'Unknown')}
ОС: {self.computer_data.get('os_name', 'Unknown')} {self.computer_data.get('os_version', '')}
CPU: {self.computer_data.get('cpu_model', 'Unknown')} ({self.computer_data.get('cpu_cores', '?')} ядер)
RAM: {self.computer_data.get('ram_total', '?')} GB
Диск: {self.computer_data.get('storage_total', '?')} GB
Статус: {"В сети" if self.computer_data.get('is_online') else "Не в сети"}"""
        
        # 2. Аномалии (только последние 10)
        anomalies_info = ""
        if self.anomalies:
            anomalies_info = "\n\nАНОМАЛИИ (последние 10):\n"
            for a in self.anomalies[-10:]:
                ts = a.get('timestamp', '')[:19]
                cpu = a.get('cpu_usage', '—')
                ram = a.get('ram_usage', '—')
                anomalies_info += f"- {ts}: CPU={cpu}%, RAM={ram}%\n"
        
        # 3. Критические ошибки и ошибки драйверов (только последние 10)
        errors_info = ""
        if self.events:
            critical_errors = []
            for event in self.events:
                event_type = event.get('type', '')
                data = event.get('data', {})
                msg = data.get('message', '') or data.get('description', '')
                if not msg:
                    continue
                msg_lower = msg.lower()
                # Берем только критические: драйверы, система, ошибки
                is_critical = any(kw in msg_lower for kw in [
                    'driver', 'драйвер', 'error', 'ошибка', 'critical', 'критич',
                    'fail', 'сбой', 'crash', 'авария', 'fatal', 'не удалось', 'failed'
                ])
                if is_critical:
                    critical_errors.append(msg[:150])
            
            if critical_errors:
                errors_info = "\n\nКРИТИЧЕСКИЕ ОШИБКИ (последние 10):\n"
                for err in critical_errors[-10:]:
                    errors_info += f"- {err}\n"
        
        # Итоговый промпт (минимальный)
        full_prompt = f"""Проанализируй состояние компьютера и дай рекомендации.

{computer_info}
{anomalies_info}
{errors_info}

Дай краткий анализ: что не так, какие ошибки нужно исправить, что рекомендуется улучшить."""
        
        return full_prompt


class AIAnalysisTab(QWidget):
    """Вкладка с AI-анализом состояния компьютера"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.analysis_thread = None
        self._cached_result = None
        self._analysis_started = False
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Верхняя панель с кнопкой и статусом
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
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
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
        
        # Приветствие (пока нет анализа)
        self.placeholder = QLabel("👋 Нажмите «Запустить AI-анализ» для получения рекомендаций")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("""
            font-size: 14px;
            color: #7f8c8d;
            padding: 50px;
        """)
        self.result_layout.addWidget(self.placeholder)
        
        self.result_area.setWidget(self.result_widget)
        layout.addWidget(self.result_area)
    
    def _on_analyze_clicked(self):
        """Обработчик клика по кнопке анализа"""
        if self._analysis_started:
            return
        self._analysis_started = True
        self.analyze_btn.setEnabled(False)
        self._do_analysis()
    
    def run_analysis(self):
        """Запускает AI-анализ при открытии окна после загрузки данных"""
        if self._cached_result:
            self._show_result(self._cached_result)
            return
        
        if self._analysis_started:
            return
        
        self._analysis_started = True
        self._do_analysis()
    
    def _do_analysis(self):
        """Запускает анализ в фоне"""
        if not self.parent_window or not self.parent_window.computer_id:
            self.placeholder.setText("❌ Невозможно выполнить анализ")
            self.placeholder.setStyleSheet("font-size: 14px; color: #e74c3c; padding: 50px;")
            return
        
        # Проверяем скорость LLM простым запросом
        self.placeholder.setText("⏳ Проверка подключения к нейросети...")
        self.placeholder.setStyleSheet("font-size: 14px; color: #8e44ad; padding: 50px;")
        
        # Запускаем тестовый запрос к LLM в отдельном потоке
        self._run_llm_test()
    
    def _run_llm_test(self):
        """Быстрый тест LLM (простой запрос), затем основной анализ"""
        import requests
        from qtpy.QtCore import QTimer
        
        try:
            url = f"{LLM_CONFIG['base_url']}/chat/completions"
            headers = {
                "Authorization": f"Bearer {LLM_CONFIG['api_key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": LLM_CONFIG["model"],
                "messages": [
                    {"role": "user", "content": "Привет! Ответь одним словом: все ли работает?"}
                ],
                "temperature": 0.1,
                "max_tokens": 10
            }
            
            import time
            start = time.time()
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                print(f"[AI] Тест LLM: {elapsed:.1f}с - OK")
                # LLM работает - запускаем реальный анализ
                self._run_real_analysis()
            else:
                self._on_analysis_error(f"Ошибка API ({response.status_code})\nПроверьте настройки LLM в constants.py")
        except requests.exceptions.Timeout:
            self._on_analysis_error("Превышено время ожидания LLM (15с)\nПроверьте подключение к нейросети")
        except requests.exceptions.ConnectionError:
            self._on_analysis_error("Нет подключения к серверу LLM\nПроверьте URL в constants.py")
        except Exception as e:
            self._on_analysis_error(f"Ошибка подключения к LLM: {e}")
    
    def _run_real_analysis(self):
        """Запускает реальный анализ с оптимизированными данными"""
        self.progress_bar.setVisible(True)
        self.status_label.setText("⏳ Загрузка данных...")
        self.status_label.setStyleSheet("color: #8e44ad; font-size: 12px;")
        
        # Загружаем данные
        metrics = self.parent_window.metrics_tab.get_current_metrics() if hasattr(self.parent_window, 'metrics_tab') else []
        events = self.parent_window.events_tab.get_all_events() if hasattr(self.parent_window, 'events_tab') else []
        anomalies = self.parent_window.anomalies_tab.anomalies if hasattr(self.parent_window, 'anomalies_tab') else []
        sessions = self.parent_window.sessions_tab.get_sessions() if hasattr(self.parent_window, 'sessions_tab') else []
        
        # Логируем объем данных для диагностики
        import json
        metrics_size = len(json.dumps(metrics)) if metrics else 0
        events_size = len(json.dumps(events)) if events else 0
        anomalies_size = len(json.dumps(anomalies)) if anomalies else 0
        
        print(f"[AI] === ОБЪЕМ ДАННЫХ ===")
        print(f"[AI] Metrics: {len(metrics)} записей, {metrics_size/1024:.1f} KB")
        print(f"[AI] Events: {len(events)} записей, {events_size/1024:.1f} KB")
        print(f"[AI] Anomalies: {len(anomalies)} записей, {anomalies_size/1024:.1f} KB")
        print(f"[AI] Всего: {(metrics_size + events_size + anomalies_size)/1024:.1f} KB")
        
        if metrics:
            print(f"[AI] Пример метрики: {metrics[0]}")
        if events:
            print(f"[AI] Пример события (первые 100 символов): {str(events[0])[:100]}")
        
        # ОГРАНИЧИВАЕМ ДАННЫЕ для ускорения
        if len(metrics) > 100:
            metrics = metrics[-100:]  # Последние 100 метрик
        if len(events) > 50:
            events = events[-50:]  # Последние 50 событий
        if len(anomalies) > 20:
            anomalies = anomalies[-20:]  # Последние 20 аномалий
        
        print(f"[AI] После ограничения: metrics={len(metrics)}, events={len(events)}, anomalies={len(anomalies)}")
        
        period = self.parent_window.date_range.get_period() if hasattr(self.parent_window, 'date_range') else {'from': '', 'to': ''}
        computer_data = self.parent_window.current_data or {}
        
        self.analysis_thread = AIAnalysisThread(
            computer_data=computer_data,
            metrics=metrics,
            events=events,
            anomalies=anomalies,
            session_info=sessions,
            period=period
        )
        
        self.analysis_thread.finished_analysis.connect(self._on_analysis_finished)
        self.analysis_thread.error_occurred.connect(self._on_analysis_error)
        self.analysis_thread.start()
    
    def _clear_result_area(self):
        """Очищает область результатов"""
        while self.result_layout.count():
            child = self.result_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _show_result(self, result):
        """Показывает кешированный результат"""
        self._clear_result_area()
        self._display_analysis_result(result)
    
    def _on_analysis_finished(self, result):
        """Отображает результат анализа и кеширует его"""
        self._cached_result = result  # Кешируем
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.status_label.setText("✅ Анализ завершен")
        self.status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        self._clear_result_area()
        self._display_analysis_result(result)
    
    def _on_analysis_error(self, error_msg):
        """Обрабатывает ошибку анализа"""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.status_label.setText("❌ Ошибка анализа")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self._clear_result_area()
        
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
