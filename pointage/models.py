"""Pointage et approvisionnement de chantier (documents Dima Groupe)."""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

ZERO = Decimal("0")


def _suivant(qs):
    return (qs.aggregate(Max("sequence"))["sequence__max"] or 0) + 1


class Chantier(models.Model):
    JOURS = [(0, "Lundi"), (1, "Mardi"), (2, "Mercredi"), (3, "Jeudi"), (4, "Vendredi"),
             (5, "Samedi"), (6, "Dimanche")]

    nom = models.CharField(max_length=200, help_text="Ex. : YAMAIL")
    code = models.CharField(max_length=10, unique=True, help_text="Préfixe des numéros. Ex. : YML")
    site = models.CharField("Site", max_length=200, blank=True, help_text="Ex. : Point E")
    client = models.CharField(max_length=200, blank=True)
    chef_projet = models.CharField("Chef de projet", max_length=150, blank=True)
    debut_semaine = models.PositiveSmallIntegerField(
        "La semaine de pointage commence le", choices=JOURS, default=5)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-actif", "nom"]

    def __str__(self):
        return self.nom

    def save(self, *a, **kw):
        self.code = self.code.strip().upper()
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("pointage:dashboard", args=[self.pk])

    def debut_de_semaine(self, jour):
        return jour - timedelta(days=(jour.weekday() - self.debut_semaine) % 7)


class Poste(models.Model):
    """Catégorie d'ouvriers dans la fiche de pointage (HSE, grutier, soudeur…)."""

    nom = models.CharField(max_length=100, unique=True)
    ordre = models.PositiveSmallIntegerField(default=0, help_text="Ordre d'affichage sur la fiche")

    class Meta:
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


class Ouvrier(models.Model):
    chantier = models.ForeignKey(Chantier, on_delete=models.CASCADE, related_name="ouvriers")
    poste = models.ForeignKey(Poste, on_delete=models.SET_NULL, null=True, blank=True, related_name="ouvriers")
    nom = models.CharField(max_length=150)
    telephone = models.CharField(max_length=50, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["poste__ordre", "poste__nom", "nom"]

    def __str__(self):
        return self.nom


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200, unique=True)
    adresse = models.CharField(max_length=255, blank=True)
    telephone = models.CharField("Tél", max_length=50, blank=True)
    email = models.EmailField("E-mail", blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


# --------------------------------------------------------------------------- #
# Demande d'approvisionnement → demande d'achat → bon de commande
# --------------------------------------------------------------------------- #
class DemandeAppro(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        ENVOYEE = "ENVOYEE", "Envoyée aux achats"
        ANNULEE = "ANNULEE", "Annulée"

    chantier = models.ForeignKey(Chantier, on_delete=models.CASCADE, related_name="demandes")
    sequence = models.PositiveIntegerField("N°", null=True, blank=True,
                                           help_text="Laisser vide pour la numérotation automatique")
    date = models.DateField(default=timezone.localdate)
    demandeur = models.CharField(max_length=150)
    fonction = models.CharField(max_length=150, blank=True)
    site = models.CharField(max_length=200, blank=True)
    urgence = models.BooleanField("Urgence", default=False)
    commentaire = models.TextField(blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ENVOYEE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-sequence"]
        constraints = [models.UniqueConstraint(fields=["chantier", "sequence"], name="da_numero_unique")]

    def save(self, *a, **kw):
        if not self.sequence:
            self.sequence = _suivant(DemandeAppro.objects.filter(chantier=self.chantier))
        if not self.site:
            self.site = self.chantier.site
        super().save(*a, **kw)

    @property
    def numero(self):
        return f"{self.chantier.code} / {self.sequence:04d}"

    def __str__(self):
        return self.numero

    def get_absolute_url(self):
        return reverse("pointage:demande_detail", args=[self.pk])

    @property
    def etat(self):
        if self.statut == "ANNULEE":
            return "Annulée"
        lignes = list(self.lignes.all())
        commandees = sum(1 for l in lignes if list(l.lignes_bc.all()))
        if lignes and commandees == len(lignes):
            return "Commandée"
        if commandees:
            return "Partiellement commandée"
        return self.get_statut_display()


class LigneAppro(models.Model):
    demande = models.ForeignKey(DemandeAppro, on_delete=models.CASCADE, related_name="lignes")
    designation = models.CharField("Désignation", max_length=250)
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    unite = models.CharField("Unité", max_length=30, default="Unité")
    specification = models.CharField("Spécification technique", max_length=300, blank=True)
    fournisseur_recommande = models.ForeignKey(
        Fournisseur, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Fournisseur recommandé")

    class Meta:
        ordering = ["id"]


class BonCommande(models.Model):
    class Statut(models.TextChoices):
        EMIS = "EMIS", "Émis"
        ANNULE = "ANNULE", "Annulé"

    chantier = models.ForeignKey(Chantier, on_delete=models.CASCADE, related_name="bons")
    demande = models.ForeignKey(DemandeAppro, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="bons")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name="bons")
    sequence = models.PositiveIntegerField("N°", null=True, blank=True,
                                           help_text="Laisser vide pour la numérotation automatique")
    date = models.DateField(default=timezone.localdate)
    date_livraison_prevue = models.DateField("Livraison prévue", null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EMIS)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-sequence"]
        constraints = [models.UniqueConstraint(fields=["chantier", "sequence"], name="bc_numero_unique")]

    def save(self, *a, **kw):
        if not self.sequence:
            self.sequence = _suivant(BonCommande.objects.filter(chantier=self.chantier))
        super().save(*a, **kw)

    @property
    def numero(self):
        return f"BC / {self.chantier.code} / {self.sequence:04d}"

    def __str__(self):
        return self.numero

    def get_absolute_url(self):
        return reverse("pointage:bon_detail", args=[self.pk])

    @property
    def total(self):
        return sum((l.prix_total for l in self.lignes.all()), ZERO)

    @property
    def livraison(self):
        lignes = list(self.lignes.all())
        if not lignes:
            return None
        if all(l.recu >= l.quantite for l in lignes):
            return "complete"
        return "partielle" if any(l.recu > 0 for l in lignes) else "aucune"

    @property
    def livraison_label(self):
        return {"aucune": "À livrer", "partielle": "Livraison partielle",
                "complete": "Livré", None: "—"}[self.livraison]


class LigneBC(models.Model):
    bon = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name="lignes")
    ligne_appro = models.ForeignKey(LigneAppro, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="lignes_bc")
    designation = models.CharField("Désignation", max_length=250)
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    unite = models.CharField("Unité", max_length=30, default="Unité")
    prix_unitaire = models.DecimalField("Prix unitaire (F CFA)", max_digits=12, decimal_places=0, default=ZERO)

    class Meta:
        ordering = ["id"]

    @property
    def prix_total(self):
        return self.quantite * self.prix_unitaire

    @property
    def recu(self):
        return sum((r.quantite for r in self.receptions.all()), ZERO)

    @property
    def reste(self):
        return max(self.quantite - self.recu, ZERO)


class Reception(models.Model):
    bon = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name="receptions")
    date = models.DateField(default=timezone.localdate)
    bon_livraison = models.CharField("N° bon de livraison", max_length=60, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "-id"]


class LigneReception(models.Model):
    reception = models.ForeignKey(Reception, on_delete=models.CASCADE, related_name="lignes")
    ligne_bc = models.ForeignKey(LigneBC, on_delete=models.CASCADE, related_name="receptions")
    quantite = models.DecimalField(max_digits=12, decimal_places=3)


# --------------------------------------------------------------------------- #
# Pointage (fiche hebdomadaire)
# --------------------------------------------------------------------------- #
class Pointage(models.Model):
    class Statut(models.TextChoices):
        PRESENT = "P", "Présent"
        ABSENT = "A", "X"

    chantier = models.ForeignKey(Chantier, on_delete=models.CASCADE, related_name="pointages")
    ouvrier = models.ForeignKey(Ouvrier, on_delete=models.CASCADE, related_name="pointages")
    date = models.DateField()
    statut = models.CharField(max_length=1, choices=Statut.choices)
    heures_sup = models.DecimalField(max_digits=4, decimal_places=1, default=ZERO)

    class Meta:
        ordering = ["-date", "ouvrier__nom"]
        constraints = [models.UniqueConstraint(fields=["ouvrier", "date"], name="un_pointage_par_jour")]
