from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(url='/pointage/', permanent=False)),  # Redirige la racine vers l'application
    path('admin/', admin.site.urls),
    path('pointage/', include('pointage.urls')),
]