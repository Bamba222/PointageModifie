from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from . import models as m


class BS:
    """Classes Bootstrap sur tous les widgets."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, forms.Select):
                w.attrs["class"] = "form-select"
            else:
                w.attrs["class"] = "form-control"
            if isinstance(w, forms.NumberInput):
                w.attrs.setdefault("step", "any")


def _date():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ChantierForm(BS, forms.ModelForm):
    class Meta:
        model = m.Chantier
        fields = ["nom", "code", "site", "client", "chef_projet", "debut_semaine", "actif"]


class PosteForm(BS, forms.ModelForm):
    class Meta:
        model = m.Poste
        fields = ["nom", "ordre"]


class OuvrierForm(BS, forms.ModelForm):
    class Meta:
        model = m.Ouvrier
        fields = ["nom", "poste", "telephone", "actif"]


class FournisseurForm(BS, forms.ModelForm):
    class Meta:
        model = m.Fournisseur
        fields = ["nom", "adresse", "telephone", "email"]


class _NumeroMixin:
    """Refuse un numéro déjà utilisé sur le chantier."""

    def __init__(self, *a, chantier=None, **kw):
        super().__init__(*a, **kw)
        self.chantier = chantier or (self.instance.chantier if self.instance.pk else None)

    def clean_sequence(self):
        n = self.cleaned_data.get("sequence")
        if n and self.chantier:
            autres = self._meta.model.objects.filter(chantier=self.chantier, sequence=n)
            if self.instance.pk:
                autres = autres.exclude(pk=self.instance.pk)
            if autres.exists():
                raise forms.ValidationError(f"Le n° {n:04d} existe déjà sur ce chantier.")
        return n


class DemandeForm(_NumeroMixin, BS, forms.ModelForm):
    class Meta:
        model = m.DemandeAppro
        fields = ["sequence", "date", "demandeur", "fonction", "site", "urgence", "statut", "commentaire"]
        widgets = {"date": _date(), "commentaire": forms.Textarea(attrs={"rows": 2})}


class LigneApproForm(BS, forms.ModelForm):
    class Meta:
        model = m.LigneAppro
        fields = ["designation", "quantite", "unite", "specification", "fournisseur_recommande"]
        widgets = {"designation": forms.TextInput(attrs={"list": "dl-designations", "autocomplete": "off"}),
                   "unite": forms.TextInput(attrs={"list": "dl-unites", "autocomplete": "off"})}

    def clean_quantite(self):
        q = self.cleaned_data["quantite"]
        if q is not None and q <= 0:
            raise forms.ValidationError("La quantité doit être positive.")
        return q


LigneApproFormSet = inlineformset_factory(
    m.DemandeAppro, m.LigneAppro, form=LigneApproForm, extra=4, min_num=1, validate_min=True, can_delete=True)


class BonForm(_NumeroMixin, BS, forms.ModelForm):
    class Meta:
        model = m.BonCommande
        fields = ["fournisseur", "sequence", "date", "date_livraison_prevue", "statut", "notes"]
        widgets = {"date": _date(), "date_livraison_prevue": _date(), "notes": forms.Textarea(attrs={"rows": 2})}


class LigneBCForm(BS, forms.ModelForm):
    class Meta:
        model = m.LigneBC
        fields = ["designation", "quantite", "unite", "prix_unitaire"]
        widgets = {"designation": forms.TextInput(attrs={"list": "dl-designations", "autocomplete": "off"}),
                   "unite": forms.TextInput(attrs={"list": "dl-unites", "autocomplete": "off"})}

    def clean_quantite(self):
        q = self.cleaned_data["quantite"]
        if q is not None and q <= 0:
            raise forms.ValidationError("La quantité doit être positive.")
        return q


LigneBCFormSet = inlineformset_factory(
    m.BonCommande, m.LigneBC, form=LigneBCForm, extra=4, min_num=1, validate_min=True, can_delete=True)


class BonDepuisDemandeForm(forms.Form):
    """Transforme une demande d'approvisionnement en bon de commande."""

    fournisseur = forms.ModelChoiceField(queryset=m.Fournisseur.objects.all(), label="Fournisseur")
    date = forms.DateField(initial=timezone.localdate, widget=_date())

    def __init__(self, demande, *a, **kw):
        super().__init__(*a, **kw)
        self.lignes = [l for l in demande.lignes.select_related("fournisseur_recommande")
                       if not list(l.lignes_bc.all())]
        recommandes = [l.fournisseur_recommande_id for l in self.lignes if l.fournisseur_recommande_id]
        if recommandes and not self.is_bound:
            self.fields["fournisseur"].initial = max(set(recommandes), key=recommandes.count)
        for l in self.lignes:
            self.fields[f"inc_{l.pk}"] = forms.BooleanField(required=False, initial=True, label="Inclure")
            self.fields[f"prix_{l.pk}"] = forms.DecimalField(
                required=False, min_value=Decimal("0"), max_digits=12, decimal_places=0, label="Prix unitaire")
        for name, f in self.fields.items():
            f.widget.attrs["class"] = ("form-check-input" if name.startswith("inc_")
                                       else "form-select" if name == "fournisseur" else "form-control")
            if isinstance(f.widget, forms.NumberInput):
                f.widget.attrs["step"] = "any"

    def clean(self):
        cd = super().clean()
        self.choisies = [(l, cd.get(f"prix_{l.pk}") or Decimal(0)) for l in self.lignes if cd.get(f"inc_{l.pk}")]
        if not self.choisies and not self.errors:
            raise forms.ValidationError("Coche au moins une ligne à commander.")
        return cd

    @property
    def cellules(self):
        return [(l, self[f"inc_{l.pk}"], self[f"prix_{l.pk}"]) for l in self.lignes]


class ReceptionForm(forms.Form):
    """Saisie d'une livraison : une quantité par ligne du bon de commande."""

    date = forms.DateField(label="Date de livraison", initial=timezone.localdate, widget=_date())
    bon_livraison = forms.CharField(label="N° bon de livraison", max_length=60, required=False)
    notes = forms.CharField(label="Remarques", max_length=255, required=False)

    def __init__(self, bon, *a, **kw):
        super().__init__(*a, **kw)
        self.lignes = list(bon.lignes.all())
        for l in self.lignes:
            self.fields[f"q_{l.pk}"] = forms.DecimalField(
                label=l.designation, min_value=Decimal("0"), max_digits=12, decimal_places=3, required=False)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"
            if isinstance(f.widget, forms.NumberInput):
                f.widget.attrs["step"] = "any"

    def clean(self):
        cd = super().clean()
        self.quantites = [(l, cd.get(f"q_{l.pk}")) for l in self.lignes if cd.get(f"q_{l.pk}")]
        if not self.quantites and not self.errors:
            raise forms.ValidationError("Saisis au moins une quantité livrée.")
        return cd

    @property
    def cellules(self):
        return [(l, self[f"q_{l.pk}"]) for l in self.lignes]
