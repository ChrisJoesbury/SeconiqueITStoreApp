"""Store roles named in the assignment brief."""

from django.contrib.auth.models import Group

STANDARD = "Standard"
ADMIN = "Admin"
REPORTING = "Reporting"
ASSIGNEE = "Assignee"

OPERATIONAL = (STANDARD, ADMIN)
REPORTING_ACCESS = (REPORTING, ADMIN)
APP_ROLES = (STANDARD, ADMIN, REPORTING)
ALL = APP_ROLES + (ASSIGNEE,)


def role_names(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    names = set(user.groups.values_list("name", flat=True))
    if user.is_superuser:
        names.add(ADMIN)
    return names


def has_role(user, roles):
    return bool(role_names(user) & set(roles))


def primary_role(user):
    names = role_names(user)
    if ADMIN in names:
        return ADMIN
    if STANDARD in names:
        return STANDARD
    if REPORTING in names:
        return REPORTING
    if ASSIGNEE in names:
        return ASSIGNEE
    return None


def set_store_role(user, role):
    """Give the user exactly one store role."""
    if role not in ALL:
        raise ValueError(role)
    keep, _created = Group.objects.get_or_create(name=role)
    drop = Group.objects.filter(name__in=ALL).exclude(pk=keep.pk)
    user.groups.remove(*drop)
    user.groups.add(keep)


def home_url_name(user):
    role = primary_role(user)
    if role == REPORTING:
        return "analytics"
    if role == ASSIGNEE:
        return "no_access"
    if role is None:
        return "no_role"
    return "dashboard"
