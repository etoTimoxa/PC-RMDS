import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication

from agent.auth_dialog import AuthDialog
from agent.remote_agent import RemoteAgentWindow
from utils.dependencies import DependencyChecker
from utils.platform_utils import ensure_dirs, get_platform_name, get_data_dir


def main():
    # Обеспечиваем создание всех необходимых директорий
    try:
        ensure_dirs()
        print(f"Платформа: {get_platform_name()}")
        print(f"Директория данных: {get_data_dir()}")
    except Exception as e:
        print(f"Ошибка инициализации: {e}")
    
    # Проверяем зависимости при запуске
    try:
        DependencyChecker.print_check_results()
    except Exception as e:
        print(f"Ошибка проверки зависимостей: {e}")
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Remote Access Agent")
    
    auth_dialog = AuthDialog()
    if auth_dialog.exec() == AuthDialog.DialogCode.Accepted:
        window = RemoteAgentWindow(auth_dialog.computer_data)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()