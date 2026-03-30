import sys
import importlib
import shutil
import subprocess
from typing import List, Dict, Tuple

class DependencyChecker:
    """Проверяет наличие необходимых зависимостей для кроссплатформенной работы"""
    
    # Обязательные Python пакеты
    REQUIRED_PACKAGES = [
        'PyQt6',
        'psutil',
        'pymysql',
        'boto3',
        'websockets',
        'pynput',
        'pyautogui',
        'mss',
        'PIL',  # Pillow
    ]
    
    # Опциональные пакеты (улучшают функциональность)
    OPTIONAL_PACKAGES = {
        'win32evtlog': 'Требуется для сбора событий Windows (только Windows)',
        'win32process': 'Требуется для работы с процессами Windows (только Windows)',
        'wmi': 'Требуется для получения информации о железе (только Windows)',
    }
    
    # Системные утилиты для Linux
    LINUX_UTILITIES = {
        'journalctl': 'Сбор системных событий (systemd)',
        'w': 'Определение активности пользователя',
        'xprintidle': 'Точное определение простоя (X11)',
    }
    
    @classmethod
    def check_required_packages(cls) -> Tuple[bool, List[str]]:
        """Проверяет наличие обязательных пакетов"""
        missing = []
        
        for package in cls.REQUIRED_PACKAGES:
            try:
                importlib.import_module(package)
            except ImportError:
                missing.append(package)
        
        return len(missing) == 0, missing
    
    @classmethod
    def check_optional_packages(cls) -> Dict[str, bool]:
        """Проверяет наличие опциональных пакетов"""
        status = {}
        
        for package, description in cls.OPTIONAL_PACKAGES.items():
            try:
                importlib.import_module(package)
                status[package] = True
            except ImportError:
                status[package] = False
        
        return status
    
    @classmethod
    def check_linux_utilities(cls) -> Dict[str, bool]:
        """Проверяет наличие системных утилит Linux"""
        if sys.platform != 'linux':
            return {}
        
        status = {}
        
        for utility, description in cls.LINUX_UTILITIES.items():
            status[utility] = shutil.which(utility) is not None
        
        return status
    
    @classmethod
    def get_system_info(cls) -> Dict:
        """Получает информацию о системе"""
        info = {
            'platform': sys.platform,
            'python_version': sys.version,
            'os': sys.platform,
        }
        
        if sys.platform == 'linux':
            # Пытаемся определить дистрибутив
            try:
                import platform
                info['distro'] = platform.freedesktop_os_release()
            except:
                try:
                    result = subprocess.run(['lsb_release', '-a'], capture_output=True, text=True)
                    info['distro_info'] = result.stdout
                except:
                    pass
        
        return info
    
    @classmethod
    def run_full_check(cls) -> Dict:
        """Запускает полную проверку зависимостей"""
        result = {
            'system': cls.get_system_info(),
            'required_packages': {},
            'optional_packages': {},
            'linux_utilities': {},
            'recommendations': []
        }
        
        # Проверяем обязательные пакеты
        all_required_ok, missing_required = cls.check_required_packages()
        result['required_packages']['ok'] = all_required_ok
        result['required_packages']['missing'] = missing_required
        
        if missing_required:
            result['recommendations'].append(
                f"Отсутствуют обязательные пакеты: {', '.join(missing_required)}. "
                f"Установите: pip install {' '.join(missing_required)}"
            )
        
        # Проверяем опциональные пакеты
        optional_status = cls.check_optional_packages()
        result['optional_packages'] = optional_status
        
        missing_optional = [pkg for pkg, ok in optional_status.items() if not ok]
        if missing_optional:
            result['recommendations'].append(
                f"Некоторые опциональные пакеты отсутствуют: {', '.join(missing_optional)}"
            )
        
        # Проверяем утилиты Linux
        if sys.platform == 'linux':
            linux_utils = cls.check_linux_utilities()
            result['linux_utilities'] = linux_utils
            
            missing_utils = [util for util, ok in linux_utils.items() if not ok]
            if missing_utils:
                result['recommendations'].append(
                    f"Некоторые системные утилиты отсутствуют: {', '.join(missing_utils)}. "
                    f"Это может повлиять на функциональность."
                )
            
            # Проверяем наличие графической оболочки
            if not any(util in linux_utils for util in ['xprintidle', 'w']):
                result['recommendations'].append(
                    "Рекомендуется установить xprintidle для точного определения активности пользователя"
                )
        
        return result
    
    @classmethod
    def print_check_results(cls):
        """Выводит результаты проверки в консоль"""
        results = cls.run_full_check()
        
        print("=" * 60)
        print("ПРОВЕРКА ЗАВИСИМОСТЕЙ")
        print("=" * 60)
        
        print(f"\nПлатформа: {results['system']['platform']}")
        print(f"Python: {results['system']['python_version']}")
        
        if 'distro' in results['system']:
            print(f"Дистрибутив: {results['system']['distro']}")
        
        print("\nОбязательные пакеты:")
        if results['required_packages']['ok']:
            print("  ✅ Все обязательные пакеты установлены")
        else:
            print(f"  ❌ Отсутствуют: {', '.join(results['required_packages']['missing'])}")
        
        print("\nОпциональные пакеты:")
        for package, installed in results['optional_packages'].items():
            status = "✅" if installed else "❌"
            print(f"  {status} {package}")
        
        if sys.platform == 'linux':
            print("\nСистемные утилиты Linux:")
            for utility, available in results['linux_utilities'].items():
                status = "✅" if available else "❌"
                print(f"  {status} {utility}")
        
        if results['recommendations']:
            print("\nРекомендации:")
            for rec in results['recommendations']:
                print(f"  • {rec}")
        
        print("\n" + "=" * 60)
        
        return results['required_packages']['ok']