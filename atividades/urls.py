from django.urls import path

from . import planner_views, views

urlpatterns = [
    path("", views.lista, name="atividades"),
    path("<int:pk>/", views.detalhe, name="atividade_detalhe"),
    path("<int:pk>/editar/", views.editar, name="atividade_editar"),
    path("<int:pk>/excluir/", views.excluir, name="atividade_excluir"),
    path("<int:pk>/restaurar/", views.restaurar, name="atividade_restaurar"),
    path("<int:pk>/comentario/", views.comentar, name="atividade_comentario"),
    path("<int:pk>/subtarefa/", views.criar_subtarefa, name="atividade_subtarefa"),
    path("<int:pk>/status/", views.mudar_status, name="atividade_status"),
    path("<int:pk>/campos/", views.atualizar_campos, name="atividade_campos"),
    path("reordenar/", views.reordenar, name="atividades_reordenar"),
    path("<int:pk>/tempo/", views.tempo_lancar, name="atividade_tempo_lancar"),
    path("tempo/<int:sid>/", views.tempo_editar, name="atividade_tempo_editar"),
    path("tempo/<int:sid>/excluir/", views.tempo_excluir, name="atividade_tempo_excluir"),
    path("<int:pk>/cronometro/", views.cronometro, name="atividade_cronometro"),
    path("planner/agua/", planner_views.agua, name="planner_agua"),
    path("planner/habito/", planner_views.habito, name="planner_habito"),
    path("planner/meta/", planner_views.meta_add, name="planner_meta_add"),
    path("planner/meta/<int:pk>/", planner_views.meta_toggle, name="planner_meta_toggle"),
    path(
        "planner/checklist/<int:pk>/",
        planner_views.checklist_toggle,
        name="planner_checklist",
    ),
    path(
        "planner/quadrante/<int:pk>/",
        planner_views.mudar_quadrante,
        name="planner_quadrante",
    ),
    path("planner/nota/", planner_views.planner_nota, name="planner_nota"),
    path("planner/tarefa/", planner_views.planner_tarefa, name="planner_tarefa"),
]
