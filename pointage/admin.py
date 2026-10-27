from django.contrib import admin

from . import models as m


class LigneApproInline(admin.TabularInline):
    model = m.LigneAppro
    extra = 0


class LigneBCInline(admin.TabularInline):
    model = m.LigneBC
    extra = 0


@admin.register(m.DemandeAppro)
class DemandeAdmin(admin.ModelAdmin):
    list_display = ("numero", "chantier", "date", "demandeur", "urgence", "statut")
    list_filter = ("chantier", "statut", "urgence")
    inlines = [LigneApproInline]


@admin.register(m.BonCommande)
class BonAdmin(admin.ModelAdmin):
    list_display = ("numero", "chantier", "fournisseur", "date", "statut")
    list_filter = ("chantier", "statut")
    inlines = [LigneBCInline]


for model in (m.Chantier, m.Poste, m.Ouvrier, m.Fournisseur, m.Pointage):
    admin.site.register(model)
