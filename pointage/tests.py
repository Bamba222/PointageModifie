from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import models as m


class Base(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("u", password="p")
        self.client.login(username="u", password="p")
        self.ch = m.Chantier.objects.create(nom="YAMAIL", code="yml", site="Point E", chef_projet="Ababacar Seck")
        self.four = m.Fournisseur.objects.create(nom="Quincaillerie Sow", adresse="Dakar", telephone="77", email="a@b.sn")


class ConnexionTests(Base):
    def test_page_connexion_et_redirection(self):
        self.client.logout()
        r = self.client.get(reverse("pointage:home"))
        self.assertRedirects(r, reverse("pointage:login") + "?next=" + reverse("pointage:home"))
        self.assertContains(self.client.get(reverse("pointage:login")), "Connexion")
        r = self.client.post(reverse("pointage:login"), {"username": "u", "password": "p"})
        self.assertRedirects(r, reverse("pointage:home"))

    def test_mauvais_mot_de_passe(self):
        self.client.logout()
        r = self.client.post(reverse("pointage:login"), {"username": "u", "password": "x"})
        self.assertContains(r, "incorrect")

    def test_accueil_et_deconnexion(self):
        self.assertContains(self.client.get(reverse("pointage:home")), "YAMAIL")
        r = self.client.post(reverse("pointage:logout"))
        self.assertRedirects(r, reverse("pointage:login"))


class DemandeTests(Base):
    def _data(self, **extra):
        data = {"sequence": "", "date": "2026-07-16", "demandeur": "Ababacar Seck",
                "fonction": "Technicien supérieur / Conducteur des travaux", "site": "", "urgence": "on",
                "statut": "ENVOYEE", "commentaire": "",
                "lignes-TOTAL_FORMS": 2, "lignes-INITIAL_FORMS": 0, "lignes-MIN_NUM_FORMS": 1, "lignes-MAX_NUM_FORMS": 1000,
                "lignes-0-designation": "Niveau antichoc", "lignes-0-quantite": "6", "lignes-0-unite": "Unité",
                "lignes-0-specification": "", "lignes-0-fournisseur_recommande": self.four.pk,
                "lignes-1-designation": "Cisailles N°48", "lignes-1-quantite": "1", "lignes-1-unite": "Unité",
                "lignes-1-specification": "", "lignes-1-fournisseur_recommande": ""}
        data.update(extra)
        prefix = m.LigneAppro._meta.get_field("demande").remote_field.get_accessor_name()
        return {k.replace("lignes-", prefix + "-"): v for k, v in data.items()}

    def _creer(self, **extra):
        return self.client.post(reverse("pointage:demande_create", args=[self.ch.pk]), self._data(**extra))

    def test_numerotation_automatique_et_manuelle(self):
        self._creer()
        self._creer()
        self._creer(sequence="10")
        self._creer()
        self.assertEqual([d.numero for d in m.DemandeAppro.objects.order_by("sequence")],
                         ["YML / 0001", "YML / 0002", "YML / 0010", "YML / 0011"])

    def test_numero_en_double_refuse(self):
        self._creer(sequence="10")
        r = self._creer(sequence="10")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "existe déjà")
        self.assertEqual(m.DemandeAppro.objects.count(), 1)

    def test_site_repris_du_chantier_et_documents(self):
        self._creer()
        d = m.DemandeAppro.objects.get()
        self.assertEqual(d.site, "Point E")
        self.assertTrue(d.urgence)
        for name in ("demande_detail", "demande_achat", "demande_update", "bon_depuis_demande"):
            self.assertEqual(self.client.get(reverse(f"pointage:{name}", args=[d.pk])).status_code, 200, name)
        page = self.client.get(reverse("pointage:demande_detail", args=[d.pk])).content.decode()
        self.assertIn("DEMANDE D&#x27;APPROVISIONNEMENT", page.replace("'", "&#x27;"))
        self.assertIn("YML / 0001", page)
        self.assertIn("Niveau antichoc", page)

    def test_demande_sans_ligne_refusee(self):
        r = self.client.post(reverse("pointage:demande_create", args=[self.ch.pk]), {
            "date": "2026-07-16", "demandeur": "X", "statut": "ENVOYEE",
            "lignes-TOTAL_FORMS": 1, "lignes-INITIAL_FORMS": 0, "lignes-MIN_NUM_FORMS": 1, "lignes-MAX_NUM_FORMS": 1000})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(m.DemandeAppro.objects.exists())

    def test_de_la_demande_au_bon_de_commande_puis_livraison(self):
        self._creer()
        d = m.DemandeAppro.objects.get()
        l1, l2 = d.lignes.all()
        self.assertEqual(d.etat, "Envoyée aux achats")
        # le fournisseur recommandé est présélectionné
        page = self.client.get(reverse("pointage:bon_depuis_demande", args=[d.pk])).content.decode()
        self.assertIn(f'value="{self.four.pk}" selected', page)
        url = reverse("pointage:bon_depuis_demande", args=[d.pk])
        # une seule ligne commandée
        r = self.client.post(url, {"fournisseur": self.four.pk, "date": "2026-07-17",
                                   f"inc_{l1.pk}": "on", f"prix_{l1.pk}": "12000"})
        self.assertEqual(r.status_code, 302)
        bon = m.BonCommande.objects.get()
        self.assertEqual(bon.numero, "BC / YML / 0001")
        self.assertEqual(bon.total, Decimal("6") * 12000)
        d = m.DemandeAppro.objects.get()
        self.assertEqual(d.etat, "Partiellement commandée")
        # la 2e ligne seule reste proposée
        page = self.client.get(url).content.decode()
        self.assertNotIn("Niveau antichoc", page)
        self.assertIn("Cisailles", page)
        self.client.post(url, {"fournisseur": self.four.pk, "date": "2026-07-18",
                               f"inc_{l2.pk}": "on", f"prix_{l2.pk}": "8000"})
        self.assertEqual(m.DemandeAppro.objects.get().etat, "Commandée")
        self.assertEqual(m.BonCommande.objects.count(), 2)
        # page imprimable du bon
        r = self.client.get(bon.get_absolute_url())
        page = r.content.decode()
        for texte in ("BON DE COMMANDE", "Quincaillerie Sow", "Prix Unitaire (F CFA)", "72\xa0000", "BC / YML / 0001"):
            self.assertIn(texte, page)
        # livraison partielle puis complète
        l = bon.lignes.get()
        lurl = reverse("pointage:livraison", args=[bon.pk])
        self.client.post(lurl, {"date": "2026-07-20", f"q_{l.pk}": "4", "bon_livraison": "BL-1"})
        self.assertEqual(m.BonCommande.objects.get(pk=bon.pk).livraison, "partielle")
        self.client.post(lurl, {"date": "2026-07-21", f"q_{l.pk}": "2"})
        self.assertEqual(m.BonCommande.objects.get(pk=bon.pk).livraison, "complete")

    def test_bon_sans_ligne_cochee_refuse(self):
        self._creer()
        d = m.DemandeAppro.objects.get()
        r = self.client.post(reverse("pointage:bon_depuis_demande", args=[d.pk]),
                             {"fournisseur": self.four.pk, "date": "2026-07-17"})
        self.assertContains(r, "au moins une ligne")
        self.assertFalse(m.BonCommande.objects.exists())

    def test_bon_direct_et_pages(self):
        prefix = m.LigneBC._meta.get_field("bon").remote_field.get_accessor_name()
        data = {"fournisseur": self.four.pk, "sequence": "", "date": "2026-07-17", "statut": "EMIS", "notes": "",
                f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-INITIAL_FORMS": 0, f"{prefix}-MIN_NUM_FORMS": 1,
                f"{prefix}-MAX_NUM_FORMS": 1000, f"{prefix}-0-designation": "Ciment", f"{prefix}-0-quantite": "100",
                f"{prefix}-0-unite": "Sac", f"{prefix}-0-prix_unitaire": "5500"}
        r = self.client.post(reverse("pointage:bon_create", args=[self.ch.pk]), data)
        self.assertEqual(r.status_code, 302)
        bon = m.BonCommande.objects.get()
        self.assertEqual(bon.total, Decimal("550000"))
        for url in (reverse("pointage:bon_list", args=[self.ch.pk]), reverse("pointage:bon_update", args=[bon.pk]),
                    reverse("pointage:livraison", args=[bon.pk]), reverse("pointage:demande_list", args=[self.ch.pk]),
                    self.ch.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class PointageTests(Base):
    def setUp(self):
        super().setUp()
        self.p1 = m.Poste.objects.create(nom="HSE", ordre=1)
        self.p2 = m.Poste.objects.create(nom="Ferrailleurs", ordre=2)
        self.a = m.Ouvrier.objects.create(chantier=self.ch, poste=self.p1, nom="Ali")
        self.b = m.Ouvrier.objects.create(chantier=self.ch, poste=self.p2, nom="Bamba")
        self.c = m.Ouvrier.objects.create(chantier=self.ch, poste=self.p2, nom="Cheikh", actif=False)
        self.url = reverse("pointage:pointage_semaine", args=[self.ch.pk])
        self.debut = date(2026, 8, 1)         # samedi

    def _post(self, **champs):
        data = {"debut": "2026-08-03"}        # un lundi de la même semaine
        data.update(champs)
        return self.client.post(self.url, data)

    def test_semaine_commence_le_samedi(self):
        r = self.client.get(self.url + "?debut=2026-08-05")
        self.assertEqual(r.context["debut"], self.debut)
        self.assertEqual(r.context["fin"], date(2026, 8, 7))
        self.assertEqual([e["nom"] for e in r.context["entetes"]], ["SAM", "DIM", "LUN", "MAR", "MER", "JEU", "VEN"])
        noms = [l["o"].nom for g in r.context["groupes"] for l in g["lignes"]]
        self.assertEqual(noms, ["Ali", "Bamba"])       # ouvrier inactif masqué

    def test_enregistrement_et_total_heures_sup(self):
        champs = {f"s_{self.a.pk}_2026-08-01": "P", f"s_{self.a.pk}_2026-08-03": "A",
                  f"s_{self.a.pk}_2026-08-07": "P", f"h_{self.a.pk}_2026-08-07": "3",
                  f"s_{self.b.pk}_2026-08-04": "P", f"h_{self.b.pk}_2026-08-04": "2,5"}
        r = self._post(**champs)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(m.Pointage.objects.count(), 4)
        r = self.client.get(self.url + "?debut=2026-08-01")
        lignes = {l["o"].nom: l for g in r.context["groupes"] for l in g["lignes"]}
        self.assertEqual(lignes["Ali"]["jours"], 2)
        self.assertEqual(lignes["Ali"]["total_hs"], "3")
        self.assertEqual(lignes["Bamba"]["total_hs"], "2.5")
        self.assertEqual(r.context["effectif"], [1, 0, 0, 1, 0, 0, 1])
        # corriger : vider une case supprime le pointage
        self._post(**{f"s_{self.a.pk}_2026-08-01": ""})
        self.assertFalse(m.Pointage.objects.filter(ouvrier=self.a).exists() and
                         m.Pointage.objects.filter(ouvrier=self.a, date=self.debut).exists())

    def test_heures_sup_sans_presence_refusees(self):
        r = self._post(**{f"h_{self.a.pk}_2026-08-02": "2"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "exigent")
        self.assertFalse(m.Pointage.objects.exists())

    def test_heures_invalides(self):
        r = self._post(**{f"s_{self.a.pk}_2026-08-02": "P", f"h_{self.a.pk}_2026-08-02": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(m.Pointage.objects.exists())

    def test_ouvrier_inactif_garde_ses_pointages(self):
        m.Pointage.objects.create(chantier=self.ch, ouvrier=self.c, date=self.debut, statut="P")
        r = self.client.get(self.url + "?debut=2026-08-01")
        noms = [l["o"].nom for g in r.context["groupes"] for l in g["lignes"]]
        self.assertIn("Cheikh", noms)

    def test_fiche_affiche_les_en_tetes(self):
        page = self.client.get(self.url + "?debut=2026-08-01").content.decode()
        for t in ("FICHE DE POINTAGE", "EN.11.RH", "CHANTIER : YAMAIL", "ABABACAR SECK", "FERRAILLEURS"):
            self.assertIn(t, page)

    def test_equipe_et_postes(self):
        for url in (reverse("pointage:equipe", args=[self.ch.pk]), reverse("pointage:ouvrier_create", args=[self.ch.pk]),
                    reverse("pointage:ouvrier_update", args=[self.a.pk]), reverse("pointage:poste_list"),
                    reverse("pointage:fournisseur_list"), reverse("pointage:fournisseur_create")):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post(reverse("pointage:ouvrier_create", args=[self.ch.pk]),
                             {"nom": "Diry Dème", "poste": self.p2.pk, "actif": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(m.Ouvrier.objects.get(nom="Diry Dème").chantier, self.ch)
