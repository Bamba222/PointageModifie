from django.urls import path

from . import views as v

app_name = "pointage"

urlpatterns = [
    path("connexion/", v.Connexion.as_view(), name="login"),
    path("deconnexion/", v.Deconnexion.as_view(), name="logout"),
    path("", v.Home.as_view(), name="home"),

    path("chantier/nouveau/", v.ChantierCreate.as_view(), name="chantier_create"),
    path("chantier/<int:pk>/", v.dashboard, name="dashboard"),
    path("chantier/<int:pk>/modifier/", v.ChantierUpdate.as_view(), name="chantier_update"),
    path("chantier/<int:pk>/supprimer/", v.ChantierDelete.as_view(), name="chantier_delete"),

    path("postes/", v.PosteList.as_view(), name="poste_list"),
    path("postes/nouveau/", v.PosteCreate.as_view(), name="poste_create"),
    path("postes/<int:pk>/modifier/", v.PosteUpdate.as_view(), name="poste_update"),
    path("fournisseurs/", v.FournisseurList.as_view(), name="fournisseur_list"),
    path("fournisseurs/nouveau/", v.FournisseurCreate.as_view(), name="fournisseur_create"),
    path("fournisseurs/<int:pk>/modifier/", v.FournisseurUpdate.as_view(), name="fournisseur_update"),

    path("chantier/<int:chantier_pk>/equipe/", v.equipe, name="equipe"),
    path("chantier/<int:chantier_pk>/equipe/nouveau/", v.OuvrierCreate.as_view(), name="ouvrier_create"),
    path("ouvrier/<int:pk>/modifier/", v.OuvrierUpdate.as_view(), name="ouvrier_update"),
    path("chantier/<int:chantier_pk>/pointage/", v.pointage_semaine, name="pointage_semaine"),

    path("chantier/<int:chantier_pk>/demandes/", v.demande_list, name="demande_list"),
    path("chantier/<int:chantier_pk>/demandes/nouvelle/", v.demande_edit, name="demande_create"),
    path("demande/<int:pk>/", v.demande_detail, name="demande_detail"),
    path("demande/<int:pk>/achat/", v.demande_detail, {"achat": True}, name="demande_achat"),
    path("demande/<int:pk>/modifier/", v.demande_edit, name="demande_update"),
    path("demande/<int:pk>/supprimer/", v.DemandeDelete.as_view(), name="demande_delete"),
    path("demande/<int:pk>/bon/", v.bon_depuis_demande, name="bon_depuis_demande"),

    path("chantier/<int:chantier_pk>/bons/", v.bon_list, name="bon_list"),
    path("chantier/<int:chantier_pk>/bons/nouveau/", v.bon_edit, name="bon_create"),
    path("bon/<int:pk>/", v.bon_detail, name="bon_detail"),
    path("bon/<int:pk>/modifier/", v.bon_edit, name="bon_update"),
    path("bon/<int:pk>/supprimer/", v.BonDelete.as_view(), name="bon_delete"),
    path("bon/<int:pk>/livraison/", v.livraison, name="livraison"),
    path("livraison/<int:pk>/supprimer/", v.livraison_delete, name="livraison_delete"),
]
