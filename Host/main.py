import sys
import os
from pathlib import Path

# Добавляем папку Host в sys.path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QMessageBox

from agent.auth_dialog import AutoAuthDialog
from agent.remote_agent import RemoteAgentWindow
from utils.admin_check import is_admin, run_as_admin


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Remote Access Agent")
    
    if not is_admin():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Требуются права администратора")
        msg.setText("Для сбора событий из журнала Windows требуются права администратора.")
        msg.setInformativeText("Перезапустить программу с правами администратора?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            run_as_admin()
            sys.exit(0)
    
    auth_dialog = AutoAuthDialog()
    if auth_dialog.exec() == AutoAuthDialog.DialogCode.Accepted:
        window = RemoteAgentWindow(auth_dialog.computer_data)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()