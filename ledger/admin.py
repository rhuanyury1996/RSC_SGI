from django.contrib import admin

from .models import Account, Category, Client, Employee, Entity, Project


class _FinAdmin(admin.ModelAdmin):
    list_filter = ("active",)
    search_fields = ("name",)


@admin.register(Entity)
class EntityAdmin(_FinAdmin):
    list_display = ("name", "kind", "effective_tax_rate_bps", "active")


@admin.register(Account)
class AccountAdmin(_FinAdmin):
    list_display = ("name", "entity", "type", "active")


@admin.register(Category)
class CategoryAdmin(_FinAdmin):
    list_display = ("name", "parent", "kind", "active")


@admin.register(Employee)
class EmployeeAdmin(_FinAdmin):
    list_display = ("name", "active")


@admin.register(Client)
class ClientAdmin(_FinAdmin):
    list_display = ("name", "active")


@admin.register(Project)
class ProjectAdmin(_FinAdmin):
    list_display = ("name", "entity", "nature", "active")
