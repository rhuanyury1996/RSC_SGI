from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

ALIQUOTA_PADRAO = Decimal("18")


class AliquotaImposto(models.Model):
    """Alíquota única de impostos sobre o valor dos negócios (registro único)."""

    percentual = models.DecimalField(
        "Alíquota (%)",
        max_digits=5,
        decimal_places=2,
        default=ALIQUOTA_PADRAO,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=(
            "Percentual aplicado sobre o valor final fechado. Vale para os negócios "
            "ganhos a partir de agora; os já ganhos mantêm a alíquota da época."
        ),
    )
    descricao = models.CharField(
        "Descrição",
        max_length=160,
        blank=True,
        help_text="Opcional. Ex.: regime tributário ou composição dos impostos.",
    )
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Alíquota de impostos"
        verbose_name_plural = "Alíquota de impostos"

    def __str__(self) -> str:
        return f"Alíquota de impostos: {self.percentual}%"

    def save(self, *args, **kwargs):
        self.pk = 1  # registro único
        super().save(*args, **kwargs)

    @classmethod
    def vigente(cls) -> Decimal:
        obj = cls.objects.filter(pk=1).only("percentual").first()
        return obj.percentual if obj else ALIQUOTA_PADRAO
