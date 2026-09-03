from django import template

register = template.Library()


@register.filter
def dictitem(mapping, key):
    return mapping.get(key)
