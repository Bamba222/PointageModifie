from django import template
from django.conf import settings

from pointage.documents import DOCS, UNITES

register = template.Library()


@register.simple_tag
def entreprise():
    return getattr(settings, "POINTAGE_ENTREPRISE", "Dima Groupe")


@register.simple_tag
def doc(nom):
    return DOCS[nom]


@register.simple_tag
def unites():
    return UNITES
