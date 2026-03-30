import sys
import os
import winreg
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                            QSpinBox, QDoubleSpinBox, QCheckBox, QTabWidget, 
                            QWidget, QDialogButtonBox)
from PyQt6.QtCore import QSettings


class SettingsDialog(QDialog):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(450)
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        tab_widget = QTabWidget()
        
        conn_tab = QWidget()
        conn_layout = QFormLayout(conn_tab)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("ws://127.0.0.1:9001")
        conn_layout.addRow("Сервер:", self.server_edit)
        tab_widget.addTab(conn_tab, "Подключение")
        
        stream_tab = QWidget()
        stream_layout = QFormLayout(stream_tab)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(30, 100)
        self.quality_spin.setSuffix("%")
        stream_layout.addRow("Качество JPEG:", self.quality_spin)
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setSingleStep(1)
        self.fps_spin.setSuffix(" FPS")
        stream_layout.addRow("Частота кадров:", self.fps_spin)
        tab_widget.addTab(stream_tab, "Трансляция")
        
        system_tab = QWidget()
        system_layout = QFormLayout(system_tab)
        self.auto_start_check = QCheckBox("Запускать при загрузке Windows")
        system_layout.addRow(self.auto_start_check)
        self.minimize_to_tray_check = QCheckBox("Сворачивать в трей при закрытии")
        system_layout.addRow(self.minimize_to_tray_check)
        self.auto_reconnect_check = QCheckBox("Автоматически подключаться к серверу")
        system_layout.addRow(self.auto_reconnect_check)
        self.auto_auth_check = QCheckBox("Автоматическая авторизация при запуске")
        system_layout.addRow(self.auto_auth_check)
        tab_widget.addTab(system_tab, "Система")
        
        layout.addWidget(tab_widget)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        self.server_edit.setText(settings.value("server", "ws://localhost:9001"))
        self.quality_spin.setValue(int(settings.value("quality", 70)))
        self.fps_spin.setValue(float(settings.value("fps", 20)))
        self.auto_start_check.setChecked(settings.value("auto_start", True, type=bool))
        self.minimize_to_tray_check.setChecked(settings.value("minimize_to_tray", True, type=bool))
        self.auto_reconnect_check.setChecked(settings.value("auto_reconnect", True, type=bool))
        self.auto_auth_check.setChecked(settings.value("auto_auth", True, type=bool))
    
    def save_settings(self):
        settings = QSettings("RemoteAccess", "Agent")
        settings.setValue("server", self.server_edit.text())
        settings.setValue("quality", self.quality_spin.value())
        settings.setValue("fps", self.fps_spin.value())
        settings.setValue("auto_start", self.auto_start_check.isChecked())
        settings.setValue("minimize_to_tray", self.minimize_to_tray_check.isChecked())
        settings.setValue("auto_reconnect", self.auto_reconnect_check.isChecked())
        settings.setValue("auto_auth", self.auto_auth_check.isChecked())
        
        if self.auto_start_check.isChecked():
            self.add_to_startup()
        else:
            self.remove_from_startup()
    
    def get_app_path(self):
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            return sys.executable
    
    def get_app_dir(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))
    
    def add_to_startup(self):
        try:
            app_path = self.get_app_path()
            app_dir = self.get_app_dir()
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            
            winreg.SetValueEx(key, "RemoteAccessAgent", 0, winreg.REG_SZ, 
                            f'"{app_path}"')
            
            winreg.CloseKey(key)
            
            startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                          r"Microsoft\Windows\Start Menu\Programs\Startup",
                                          "remote_access_agent_start.bat")
            
            with open(startup_script, 'w') as f:
                f.write(f'@echo off\n')
                f.write(f'cd /d "{app_dir}"\n')
                f.write(f'start "" "{app_path}"\n')
            
        except:
            pass
    
    def remove_from_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "RemoteAccessAgent")
            except:
                pass
            winreg.CloseKey(key)
            
            startup_script = os.path.join(os.environ.get("APPDATA", ""), 
                                          r"Microsoft\Windows\Start Menu\Programs\Startup",
                                          "remote_access_agent_start.bat")
            if os.path.exists(startup_script):
                os.remove(startup_script)
        except:
            pass