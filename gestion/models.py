from django.db import models

class Engin(models.Model):
    STATUT_CHOICES = [
        ("ACTIF", "Actif"),
        ("MAINT", "En maintenance"),
        ("PANNE", "En panne"),
    ]

    numero_serie = models.CharField(max_length=50, unique=True)
    type_engin = models.CharField(max_length=50)  # grue, pelleteuse...
    heures_moteur = models.PositiveIntegerField(default=0)
    date_mise_en_service = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default="ACTIF")

    def __str__(self):
        return f"{self.type_engin} - {self.numero_serie}"


class PieceDetachee(models.Model):
    libelle = models.CharField(max_length=80)
    reference = models.CharField(max_length=50, unique=True)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.libelle} ({self.reference})"


class Intervention(models.Model):
    TYPE_CHOICES = [
        ("PREV", "Préventive"),
        ("CORR", "Corrective"),
    ]

    engin = models.ForeignKey(Engin, on_delete=models.CASCADE, related_name="interventions")
    date_intervention = models.DateField()
    type_intervention = models.CharField(max_length=5, choices=TYPE_CHOICES)
    cout = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)

    pieces = models.ManyToManyField(PieceDetachee, through="InterventionPiece", blank=True)

    def __str__(self):
        return f"Intervention {self.get_type_intervention_display()} ({self.date_intervention})"


class InterventionPiece(models.Model):
    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE)
    piece = models.ForeignKey(PieceDetachee, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("intervention", "piece")

    def __str__(self):
        return f"{self.piece.reference} x{self.quantite}"
