from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SGI RSC"
admin.site.site_title = "SGI RSC"
admin.site.index_title = "Gestão Interna"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("funcionarios.urls")),
    path("apontamentos/", include("apontamentos.urls")),
    path("calendario/", include("calendario.urls")),
    path("informativos/", include("informativos.urls")),
    path("comercial/", include("crm.urls")),
    path("atividades/", include("atividades.urls")),
    path("pagamentos/", include("pagamentos.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
