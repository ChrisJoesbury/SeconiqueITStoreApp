from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import StoreUserForm
from ..roles import ADMIN, ALL, primary_role
from .common import paginate, role_required


def _stored_role(user):
    names = set(user.groups.values_list("name", flat=True))
    for role in ALL:
        if role in names:
            return role
    return ADMIN


@role_required(ADMIN)
def user_list(request):
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    accounts = get_user_model().objects.prefetch_related("groups").order_by("username")
    if query:
        accounts = accounts.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if role == ADMIN:
        accounts = accounts.filter(Q(groups__name=ADMIN) | Q(is_superuser=True)).distinct()
    elif role in ALL:
        accounts = accounts.filter(groups__name=role, is_superuser=False).distinct()
    page = paginate(request, accounts)
    for account in page.object_list:
        account.store_role_label = primary_role(account) or "No role"
    return render(
        request,
        "stockroom/users/list.html",
        {"page_obj": page, "query": query, "role": role, "roles": ALL},
    )


@role_required(ADMIN)
def user_create(request):
    if request.method == "POST":
        form = StoreUserForm(request.POST, actor=request.user)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"{account.username} can now sign in.")
            return redirect("user_list")
    else:
        form = StoreUserForm(actor=request.user)
    return render(request, "stockroom/users/form.html", {"form": form, "mode": "create"})


@role_required(ADMIN)
def user_edit(request, user_id):
    account = get_object_or_404(get_user_model(), pk=user_id)
    if request.method == "POST":
        form = StoreUserForm(request.POST, user=account, actor=request.user)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"{account.username} updated.")
            return redirect("user_list")
    else:
        form = StoreUserForm(
            user=account,
            actor=request.user,
            initial={
                "username": account.username,
                "first_name": account.first_name,
                "last_name": account.last_name,
                "email": account.email,
                "role": _stored_role(account),
                "is_active": account.is_active,
            },
        )
    return render(
        request,
        "stockroom/users/form.html",
        {"form": form, "mode": "edit", "account": account},
    )
