"""Модуль детальной информации о компьютере"""

from .main_window import ComputerDetailsWindow
from .dialogs import EditComputerDialog, EditSessionDialog, DateRangeDialog

__all__ = [
    'ComputerDetailsWindow',
    'EditComputerDialog',
    'EditSessionDialog',
    'DateRangeDialog'
]