"""Модуль администраторского интерфейса"""

from .admin_panel import AdminPanelWindow
from .auth_dialog import AuthDialog, ResetPasswordDialog, HardwareRegisterDialog, ClientAuthDialog
from .computer_details import ComputerDetailsWindow, EditComputerDialog, EditSessionDialog

__all__ = [
    'AdminPanelWindow',
    'AuthDialog',
    'ResetPasswordDialog',
    'HardwareRegisterDialog',
    'ClientAuthDialog',
    'ComputerDetailsWindow',
    'EditComputerDialog',
    'EditSessionDialog'
]