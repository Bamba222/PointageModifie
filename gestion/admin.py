from django.contrib import admin
from .models import Engin, Intervention, PieceDetachee, InterventionPiece

class InterventionPieceInline(admin.TabularInline):
    model = InterventionPiece
    extra = 1

@admin.register(Engin)
class EnginAdmin(admin.ModelAdmin):
    list_display = ("numero_serie", "type_engin", "heures_moteur", "statut", "date_mise_en_service")
    search_fields = ("numero_serie", "type_engin")
    list_filter = ("statut", "type_engin")

@admin.register(PieceDetachee)
class PieceDetacheeAdmin(admin.ModelAdmin):
    list_display = ("reference", "libelle", "prix_unitaire")
    search_fields = ("reference", "libelle")

@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ("engin", "date_intervention", "type_intervention", "cout")
    list_filter = ("type_intervention", "date_intervention")
    search_fields = ("engin__numero_serie", "description")
    inlines = [InterventionPieceInline]
