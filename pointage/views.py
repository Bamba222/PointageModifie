from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from . import forms, models as m
from .auth import Connecte, login_required
from .documents import JOURS_COURTS


# --------------------------------------------------------------------------- #
# Entrée : connexion, accueil
# --------------------------------------------------------------------------- #
class Connexion(LoginView):
    template_name = "pointage/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse("pointage:home")


class Deconnexion(LogoutView):
    next_page = reverse_lazy("pointage:login")


class Home(Connecte, ListView):
    template_name = "pointage/home.html"

    def get_queryset(self):
        return m.Chantier.objects.all()

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        today = timezone.localdate()
        cartes = []
        for c in ctx["object_list"]:
            bons = c.bons.exclude(statut="ANNULE").prefetch_related("lignes__receptions")
            cartes.append({
                "c": c,
                "demandes": c.demandes.filter(statut="ENVOYEE").count(),
                "urgentes": c.demandes.filter(statut="ENVOYEE", urgence=True).count(),
                "a_livrer": sum(1 for b in bons if b.livraison in ("aucune", "partielle")),
                "presents": c.pointages.filter(date=today, statut="P").count(),
                "equipe": c.ouvriers.filter(actif=True).count(),
            })
        ctx.update(cartes=cartes, today=today)
        return ctx


# --------------------------------------------------------------------------- #
# Briques génériques
# --------------------------------------------------------------------------- #
class FormPage(Connecte):
    template_name = "pointage/form.html"
    title = ""

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(title=self.title, back_url=self.get_back_url())
        return ctx

    def get_back_url(self):
        return reverse("pointage:home")


class Supprimer(Connecte, DeleteView):
    template_name = "pointage/confirm_delete.html"


def _chantier(pk):
    return get_object_or_404(m.Chantier, pk=pk)


# --------------------------------------------------------------------------- #
# Chantiers
# --------------------------------------------------------------------------- #
class ChantierCreate(FormPage, CreateView):
    model, form_class, title = m.Chantier, forms.ChantierForm, "Nouveau chantier"


class ChantierUpdate(FormPage, UpdateView):
    model, form_class, title = m.Chantier, forms.ChantierForm, "Modifier le chantier"

    def get_back_url(self):
        return self.object.get_absolute_url()


class ChantierDelete(Supprimer):
    model = m.Chantier
    success_url = reverse_lazy("pointage:home")


@login_required
def dashboard(request, pk):
    ch = _chantier(pk)
    today = timezone.localdate()
    debut = ch.debut_de_semaine(today)
    pointes = ch.pointages.filter(date__range=(debut, debut + timedelta(days=6)))
    bons = list(ch.bons.exclude(statut="ANNULE").select_related("fournisseur").prefetch_related("lignes__receptions"))
    return render(request, "pointage/dashboard.html", {
        "ch": ch, "today": today, "debut": debut, "fin": debut + timedelta(days=6),
        "presents_jour": ch.pointages.filter(date=today, statut="P").count(),
        "equipe": ch.ouvriers.filter(actif=True).count(),
        "hs_semaine": sum((p.heures_sup for p in pointes), Decimal(0)),
        "demandes": ch.demandes.filter(statut="ENVOYEE").prefetch_related("lignes__lignes_bc")[:6],
        "a_livrer": [b for b in bons if b.livraison in ("aucune", "partielle")][:6],
    })


# --------------------------------------------------------------------------- #
# Référentiels : postes, fournisseurs
# --------------------------------------------------------------------------- #
def _crud(model, form, nom, singulier, colonnes, url):
    class Liste(Connecte, ListView):
        template_name = "pointage/crud_list.html"

        def get_queryset(self):
            return model.objects.all()

        def get_context_data(self, **kw):
            ctx = super().get_context_data(**kw)
            ctx.update(titre=nom, singulier=singulier, url_create=f"pointage:{url}_create",
                       url_update=f"pointage:{url}_update", entetes=[c[0] for c in colonnes],
                       lignes=[(o, [c[1](o) for c in colonnes]) for o in ctx["object_list"]])
            return ctx

    class Creer(FormPage, CreateView):
        title = f"Nouveau {singulier}"
        success_url = reverse_lazy(f"pointage:{url}_list")

        def get_back_url(self):
            return reverse(f"pointage:{url}_list")

    class Modifier(FormPage, UpdateView):
        title = f"Modifier {singulier}"
        success_url = reverse_lazy(f"pointage:{url}_list")

        def get_back_url(self):
            return reverse(f"pointage:{url}_list")

    Creer.model = Modifier.model = Liste.model = model
    Creer.form_class = Modifier.form_class = form
    return Liste, Creer, Modifier


PosteList, PosteCreate, PosteUpdate = _crud(
    m.Poste, forms.PosteForm, "Postes (catégories d'ouvriers)", "poste",
    [("Poste", lambda o: o.nom), ("Ordre sur la fiche", lambda o: o.ordre)], "poste")
FournisseurList, FournisseurCreate, FournisseurUpdate = _crud(
    m.Fournisseur, forms.FournisseurForm, "Fournisseurs", "fournisseur",
    [("Nom", lambda o: o.nom), ("Adresse", lambda o: o.adresse), ("Tél", lambda o: o.telephone),
     ("E-mail", lambda o: o.email)], "fournisseur")


# --------------------------------------------------------------------------- #
# Équipe (ouvriers d'un chantier)
# --------------------------------------------------------------------------- #
@login_required
def equipe(request, chantier_pk):
    ch = _chantier(chantier_pk)
    groupes = {}
    for o in ch.ouvriers.select_related("poste"):
        groupes.setdefault(o.poste, []).append(o)
    return render(request, "pointage/equipe.html", {"ch": ch, "groupes": list(groupes.items())})


class OuvrierCreate(FormPage, CreateView):
    model, form_class, title = m.Ouvrier, forms.OuvrierForm, "Nouvel ouvrier"

    def dispatch(self, request, *a, **kw):
        self.ch = _chantier(kw["chantier_pk"])
        return super().dispatch(request, *a, **kw)

    def form_valid(self, form):
        form.instance.chantier = self.ch
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pointage:equipe", args=[self.ch.pk])

    def get_back_url(self):
        return self.get_success_url()


class OuvrierUpdate(FormPage, UpdateView):
    model, form_class, title = m.Ouvrier, forms.OuvrierForm, "Modifier l'ouvrier"

    def get_success_url(self):
        return reverse("pointage:equipe", args=[self.object.chantier_id])

    get_back_url = get_success_url


# --------------------------------------------------------------------------- #
# Fiche de pointage hebdomadaire
# --------------------------------------------------------------------------- #
def _date_param(valeur, defaut):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


def _fmt(h):
    return "" if not h else f"{h:f}".rstrip("0").rstrip(".")


@login_required
def pointage_semaine(request, chantier_pk):
    ch = _chantier(chantier_pk)
    ref = _date_param(request.GET.get("debut") or request.POST.get("debut"), timezone.localdate())
    debut = ch.debut_de_semaine(ref)
    jours = [debut + timedelta(days=i) for i in range(8)]   # 8 jours : SAM → SAM suivant (présence)
    fin = jours[6]                                           # fin de semaine (VEN) pour l'affichage
    ouvriers = list(ch.ouvriers.filter(Q(actif=True) | Q(pointages__date__range=(debut, jours[-1])))
                    .distinct().select_related("poste"))
    existants = {(p.ouvrier_id, p.date): (p.statut, p.heures_sup)
                 for p in m.Pointage.objects.filter(ouvrier__chantier=ch, date__range=(debut, jours[-1]))}
    etat = existants

    if request.method == "POST":
        etat, erreurs = {}, []
        for o in ouvriers:
            for j in jours:
                iso = j.isoformat()
                s = request.POST.get(f"s_{o.pk}_{iso}", "")
                brut = request.POST.get(f"h_{o.pk}_{iso}", "").strip().replace(",", ".")
                try:
                    hs = Decimal(brut) if brut else Decimal(0)
                    if hs < 0 or hs > 24:
                        raise InvalidOperation
                except InvalidOperation:
                    erreurs.append(f"{o.nom}, {j:%d/%m} : heures supplémentaires invalides.")
                    hs = Decimal(0)
                if s not in ("", "P", "A"):
                    s = ""
                if hs > 0 and s != "P":
                    erreurs.append(f"{o.nom}, {j:%d/%m} : des heures sup. exigent « Présent ».")
                if s:
                    etat[(o.pk, j)] = (s, hs)
        if not erreurs:
            with transaction.atomic():
                for o in ouvriers:
                    for j in jours:
                        if (o.pk, j) in etat:
                            s, hs = etat[(o.pk, j)]
                            m.Pointage.objects.update_or_create(
                                ouvrier=o, date=j, defaults={"chantier": ch, "statut": s, "heures_sup": hs})
                        else:
                            m.Pointage.objects.filter(ouvrier=o, date=j).delete()
            messages.success(request, f"Fiche de pointage du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} enregistrée.")
            return redirect(f"{reverse('pointage:pointage_semaine', args=[ch.pk])}?debut={debut.isoformat()}")
        for e in erreurs:
            messages.error(request, e)

    groupes, effectif = [], [0] * 8
    for o in ouvriers:
        cellules, total_hs, nb_jours = [], Decimal(0), 0
        for i, j in enumerate(jours):
            s, hs = etat.get((o.pk, j), ("", Decimal(0)))
            cellules.append({"iso": j.isoformat(), "statut": s, "hs": _fmt(hs)})
            if i < 7:                      # le 8e jour (samedi suivant) n'a pas de colonne H. sup.
                total_hs += hs
            if s == "P":
                effectif[i] += 1
                nb_jours += 1
        ligne = {"o": o, "cellules": cellules, "total_hs": _fmt(total_hs) or "0", "jours": nb_jours}
        if not groupes or groupes[-1]["poste"] != o.poste:
            groupes.append({"poste": o.poste, "lignes": []})
        groupes[-1]["lignes"].append(ligne)

    return render(request, "pointage/pointage_semaine.html", {
        "ch": ch, "debut": debut, "fin": fin, "precedente": debut - timedelta(days=7),
        "suivante": debut + timedelta(days=7), "effectif": effectif,
        "entetes": [{"d": j, "nom": JOURS_COURTS[j.weekday()]} for j in jours],
        "groupes": groupes, "nb_ouvriers": len(ouvriers),
        "total_hs": sum((Decimal(l["total_hs"]) for g in groupes for l in g["lignes"]), Decimal(0)),
    })


# --------------------------------------------------------------------------- #
# Demandes d'approvisionnement / d'achat
# --------------------------------------------------------------------------- #
def _suggestions(ch):
    designations = set(m.LigneAppro.objects.filter(demande__chantier=ch).values_list("designation", flat=True))
    designations |= set(m.LigneBC.objects.filter(bon__chantier=ch).values_list("designation", flat=True))
    return sorted(designations, key=str.lower)


@login_required
def demande_list(request, chantier_pk):
    ch = _chantier(chantier_pk)
    demandes = ch.demandes.prefetch_related("lignes__lignes_bc")
    return render(request, "pointage/demande_list.html", {"ch": ch, "demandes": demandes})


@login_required
def demande_edit(request, chantier_pk=None, pk=None):
    if pk:
        demande = get_object_or_404(m.DemandeAppro, pk=pk)
        ch = demande.chantier
    else:
        ch = _chantier(chantier_pk)
        demande = m.DemandeAppro(chantier=ch, site=ch.site, statut="ENVOYEE")
        demande.demandeur = request.user.get_full_name() or ""
    form = forms.DemandeForm(request.POST or None, instance=demande, chantier=ch)
    formset = forms.LigneApproFormSet(request.POST or None, instance=demande)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.instance = form.instance
            formset.save()
        return redirect(form.instance)
    return render(request, "pointage/demande_form.html", {
        "ch": ch, "form": form, "formset": formset, "demande": demande if pk else None,
        "suggestions": _suggestions(ch),
        "title": f"Modifier la demande {demande.numero}" if pk else "Nouvelle demande d'approvisionnement"})


@login_required
def demande_detail(request, pk, achat=False):
    d = get_object_or_404(
        m.DemandeAppro.objects.select_related("chantier")
        .prefetch_related("lignes__fournisseur_recommande", "lignes__lignes_bc", "bons__fournisseur"), pk=pk)
    return render(request, "pointage/demande_achat.html" if achat else "pointage/demande_detail.html",
                  {"d": d, "ch": d.chantier})


class DemandeDelete(Supprimer):
    model = m.DemandeAppro

    def get_success_url(self):
        return reverse("pointage:demande_list", args=[self.object.chantier_id])


@login_required
def bon_depuis_demande(request, pk):
    d = get_object_or_404(m.DemandeAppro, pk=pk)
    form = forms.BonDepuisDemandeForm(d, request.POST or None)
    if not form.lignes:
        messages.info(request, "Toutes les lignes de cette demande sont déjà commandées.")
        return redirect(d)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            bon = m.BonCommande.objects.create(
                chantier=d.chantier, demande=d, fournisseur=form.cleaned_data["fournisseur"],
                date=form.cleaned_data["date"])
            for l, prix in form.choisies:
                m.LigneBC.objects.create(bon=bon, ligne_appro=l, designation=l.designation,
                                         quantite=l.quantite, unite=l.unite, prix_unitaire=prix)
        messages.success(request, f"Bon de commande {bon.numero} créé.")
        return redirect(bon)
    return render(request, "pointage/bon_depuis_demande.html", {"d": d, "ch": d.chantier, "form": form})


# --------------------------------------------------------------------------- #
# Bons de commande & livraisons
# --------------------------------------------------------------------------- #
@login_required
def bon_list(request, chantier_pk):
    ch = _chantier(chantier_pk)
    bons = ch.bons.select_related("fournisseur").prefetch_related("lignes__receptions")
    return render(request, "pointage/bon_list.html", {"ch": ch, "bons": bons})


@login_required
def bon_edit(request, chantier_pk=None, pk=None):
    if pk:
        bon = get_object_or_404(m.BonCommande, pk=pk)
        ch = bon.chantier
    else:
        ch = _chantier(chantier_pk)
        bon = m.BonCommande(chantier=ch)
    form = forms.BonForm(request.POST or None, instance=bon, chantier=ch)
    formset = forms.LigneBCFormSet(request.POST or None, instance=bon)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.instance = form.instance
            formset.save()
        return redirect(form.instance)
    return render(request, "pointage/bon_form.html", {
        "ch": ch, "form": form, "formset": formset, "bon": bon if pk else None,
        "suggestions": _suggestions(ch),
        "title": f"Modifier {bon.numero}" if pk else "Nouveau bon de commande"})


@login_required
def bon_detail(request, pk):
    b = get_object_or_404(
        m.BonCommande.objects.select_related("chantier", "fournisseur", "demande")
        .prefetch_related("lignes__receptions", "receptions__lignes__ligne_bc"), pk=pk)
    return render(request, "pointage/bon_detail.html", {"b": b, "ch": b.chantier})


class BonDelete(Supprimer):
    model = m.BonCommande

    def get_success_url(self):
        return reverse("pointage:bon_list", args=[self.object.chantier_id])


@login_required
def livraison(request, pk):
    bon = get_object_or_404(m.BonCommande, pk=pk)
    form = forms.ReceptionForm(bon, request.POST or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        with transaction.atomic():
            rec = m.Reception.objects.create(bon=bon, date=cd["date"], bon_livraison=cd["bon_livraison"],
                                             notes=cd["notes"])
            for l, q in form.quantites:
                m.LigneReception.objects.create(reception=rec, ligne_bc=l, quantite=q)
        messages.success(request, "Livraison enregistrée.")
        return redirect(bon)
    return render(request, "pointage/livraison_form.html", {"b": bon, "ch": bon.chantier, "form": form})


@login_required
def livraison_delete(request, pk):
    rec = get_object_or_404(m.Reception, pk=pk)
    bon = rec.bon
    if request.method == "POST":
        rec.delete()
        messages.success(request, "Livraison supprimée.")
    return redirect(bon)
