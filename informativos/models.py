from django.conf import settings
from django.db import models


class CategoriaInformativo(models.TextChoices):
    FERIADOS = "feriados", "Feriados"
    FERIAS = "ferias", "Férias"
    DAY_OFF = "day_off", "Day-off"
    ANIVERSARIO = "aniversario", "Aniversário"
    VIAGEM = "viagem", "Viagem"
    NOVIDADES = "novidades", "Novidades da empresa"
    ALERTA = "alerta", "Alerta"


class Informativo(models.Model):
    titulo = models.CharField("Título", max_length=200, blank=True)
    conteudo = models.TextField("Mensagem")
    categoria = models.CharField(
        "Categoria",
        max_length=20,
        choices=CategoriaInformativo.choices,
        default=CategoriaInformativo.NOVIDADES,
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="informativos",
        verbose_name="Autor",
    )
    publicado_em = models.DateTimeField("Publicado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Informativo"
        verbose_name_plural = "Informativos"
        ordering = ["-publicado_em"]

    def __str__(self) -> str:
        return self.titulo or self.conteudo[:60]

    def save(self, *args, **kwargs):
        if not self.titulo and self.conteudo:
            texto = " ".join(self.conteudo.split())
            self.titulo = texto[:80] + ("…" if len(texto) > 80 else "")
        super().save(*args, **kwargs)

    @property
    def cor_categoria(self) -> str:
        return {
            CategoriaInformativo.FERIADOS: "#0ea5e9",
            CategoriaInformativo.FERIAS: "#14b8a6",
            CategoriaInformativo.DAY_OFF: "#ff6b4a",
            CategoriaInformativo.ANIVERSARIO: "#ec4899",
            CategoriaInformativo.VIAGEM: "#8b5cf6",
            CategoriaInformativo.NOVIDADES: "#2563eb",
            CategoriaInformativo.ALERTA: "#dc2626",
        }.get(self.categoria, "#6b7280")
