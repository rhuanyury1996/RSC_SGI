from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = "SGI RSC"
admin.site.site_title = "SGI RSC"
admin.site.index_title = "Gestão Interna"
# Segurança: só superusuário ativo entra no /admin
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("funcionarios.urls")),
    path("apontamentos/", include("apontamentos.urls")),
    path("calendario/", include("calendario.urls")),
    path("informativos/", include("informativos.urls")),
    path("comercial/", include("crm.urls")),
    path("atividades/", include("atividades.urls")),
    path("pagamentos/", include("pagamentos.urls")),
    path("orcamentos/", include("orcamentos.urls")),
]

# Media: em DEBUG usa o helper; em produção serve via view (disco do Render é efêmero)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
