from django.contrib.auth.decorators import login_required as _login_required
from django.contrib.auth.mixins import LoginRequiredMixin

LOGIN = "pointage:login"


def login_required(view):
    """Redirige vers la page de connexion du module."""
    return _login_required(login_url=LOGIN)(view)


class Connecte(LoginRequiredMixin):
    login_url = LOGIN
