from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Cargo(models.TextChoices):
    GERENTE = "gerente", "Gerente"
    SOCIO = "socio", "Sócio"
    SUPERVISOR = "supervisor", "Supervisor"
    EXECUTIVO = "executivo", "Executivo"
    ESTAGIARIO = "estagiario", "Estagiário(a)"


class CentroCusto(models.TextChoices):
    RSC = "rsc", "RSC"
    BLENDDYN = "blenddyn", "BlendDyn"
    VEO = "veo", "VEO"


class Setor(models.TextChoices):
    COMERCIAL = "comercial", "Comercial"
    FINANCEIRO = "financeiro", "Financeiro"
    GESTAO = "gestao", "Gestão"
    DESENVOLVIMENTO = "desenvolvimento", "Desenvolvimento"


class NivelAcesso(models.TextChoices):
    EDITAR = "editar", "Ver e editar"
    VER = "ver", "Só ver"
    NENHUM = "nenhum", "Sem acesso"


def _campo_acesso(rotulo: str):
    return models.CharField(
        rotulo,
        max_length=10,
        choices=NivelAcesso.choices,
        default=NivelAcesso.EDITAR,
    )


class SignoSolar(models.TextChoices):
    ARIES = "aries", "Áries"
    TOURO = "touro", "Touro"
    GEMEOS = "gemeos", "Gêmeos"
    CANCER = "cancer", "Câncer"
    LEAO = "leao", "Leão"
    VIRGEM = "virgem", "Virgem"
    LIBRA = "libra", "Libra"
    ESCORPIAO = "escorpiao", "Escorpião"
    SAGITARIO = "sagitario", "Sagitário"
    CAPRICORNIO = "capricornio", "Capricórnio"
    AQUARIO = "aquario", "Aquário"
    PEIXES = "peixes", "Peixes"


def signo_solar_por_data(dia: date) -> str:
    """Retorna a chave do signo solar tropical para a data de nascimento."""
    m, d = dia.month, dia.day
    faixas = (
        ((3, 21), (4, 19), SignoSolar.ARIES),
        ((4, 20), (5, 20), SignoSolar.TOURO),
        ((5, 21), (6, 20), SignoSolar.GEMEOS),
        ((6, 21), (7, 22), SignoSolar.CANCER),
        ((7, 23), (8, 22), SignoSolar.LEAO),
        ((8, 23), (9, 22), SignoSolar.VIRGEM),
        ((9, 23), (10, 22), SignoSolar.LIBRA),
        ((10, 23), (11, 21), SignoSolar.ESCORPIAO),
        ((11, 22), (12, 21), SignoSolar.SAGITARIO),
        ((12, 22), (12, 31), SignoSolar.CAPRICORNIO),
        ((1, 1), (1, 19), SignoSolar.CAPRICORNIO),
        ((1, 20), (2, 18), SignoSolar.AQUARIO),
        ((2, 19), (3, 20), SignoSolar.PEIXES),
    )
    for (mi, di), (mf, df), signo in faixas:
        if (m, d) >= (mi, di) and (m, d) <= (mf, df):
            return signo
    return SignoSolar.ARIES


# weekday(): 0=segunda … 4=sexta
DIAS_JORNADA = (
    (0, "trabalha_segunda", "Segunda"),
    (1, "trabalha_terca", "Terça"),
    (2, "trabalha_quarta", "Quarta"),
    (3, "trabalha_quinta", "Quinta"),
    (4, "trabalha_sexta", "Sexta"),
)


class Funcionario(models.Model):
    nome = models.CharField("Nome", max_length=100)
    sobrenome = models.CharField("Sobrenome", max_length=100)
    data_nascimento = models.DateField("Data de nascimento")
    signo_solar = models.CharField(
        "Signo solar",
        max_length=20,
        choices=SignoSolar.choices,
        blank=True,
        default="",
    )
    foto_perfil = models.ImageField(
        "Foto de perfil",
        upload_to="funcionarios/fotos/",
        blank=True,
        null=True,
    )
    # Data URI persistente (Render não mantém arquivos em disco entre deploys)
    foto_perfil_data = models.TextField(
        "Foto de perfil (dados)",
        blank=True,
        default="",
    )
    cargo = models.CharField("Cargo", max_length=20, choices=Cargo.choices)
    setor = models.CharField(
        "Setor",
        max_length=20,
        choices=Setor.choices,
        default=Setor.GESTAO,
        help_text="Usado depois para liberar ou travar páginas por área.",
    )
    responde_a = models.ForeignKey(
        "self",
        verbose_name="A quem responde",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinados",
    )
    centro_custo = models.CharField(
        "Centro de custo",
        max_length=20,
        choices=CentroCusto.choices,
    )
    trabalha_segunda = models.BooleanField("Segunda", default=True)
    trabalha_terca = models.BooleanField("Terça", default=True)
    trabalha_quarta = models.BooleanField("Quarta", default=True)
    trabalha_quinta = models.BooleanField("Quinta", default=True)
    trabalha_sexta = models.BooleanField("Sexta", default=True)
    hora_entrada = models.TimeField("Horário de entrada", default=time(9, 15))
    hora_saida = models.TimeField("Horário de saída", default=time(17, 0))
    intervalo_almoco_minutos = models.PositiveSmallIntegerField(
        "Intervalo de almoço (minutos)",
        default=45,
        help_text="Descontado da jornada líquida esperada no dia.",
    )
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuário do sistema",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="funcionario",
    )
    ativo = models.BooleanField("Ativo", default=True)
    # Acesso por módulo (ver funcionarios/acessos.py)
    acesso_comercial = _campo_acesso("Comercial (CRM)")
    acesso_orcamentos = _campo_acesso("Orçamentos")
    acesso_atividades = _campo_acesso("Atividades")
    acesso_apontamentos = _campo_acesso("Apontamentos")
    acesso_calendario = _campo_acesso("Calendário")
    acesso_informativos = _campo_acesso("Informativos")
    acesso_pagamentos = _campo_acesso("Pagamentos")
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Funcionário"
        verbose_name_plural = "Funcionários"
        ordering = ["nome", "sobrenome"]

    def __str__(self) -> str:
        return f"{self.nome} {self.sobrenome}"

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.sobrenome}"

    @property
    def tem_foto(self) -> bool:
        if self.foto_perfil_data and self.foto_perfil_data.startswith("data:image"):
            return True
        if self.foto_perfil and self.foto_perfil.name:
            try:
                return self.foto_perfil.storage.exists(self.foto_perfil.name)
            except Exception:
                return False
        return False

    @property
    def foto_url(self) -> str:
        """URL da foto: data URI no banco (produção) ou arquivo em MEDIA."""
        if self.foto_perfil_data and self.foto_perfil_data.startswith("data:image"):
            return self.foto_perfil_data
        if self.foto_perfil and self.foto_perfil.name:
            try:
                if self.foto_perfil.storage.exists(self.foto_perfil.name):
                    return self.foto_perfil.url
            except Exception:
                return ""
        return ""

    @property
    def signo_sugerido(self) -> str:
        if not self.data_nascimento:
            return ""
        return signo_solar_por_data(self.data_nascimento)

    def clean(self):
        super().clean()
        if self.hora_entrada and self.hora_saida and self.hora_saida <= self.hora_entrada:
            raise ValidationError(
                {"hora_saida": "A saída deve ser posterior à entrada."}
            )
        bruto = self._segundos_brutos_dia()
        intervalo = int(self.intervalo_almoco_minutos or 0) * 60
        if bruto > 0 and intervalo >= bruto:
            raise ValidationError(
                {
                    "intervalo_almoco_minutos": (
                        "O intervalo de almoço deve ser menor que a jornada bruta."
                    )
                }
            )

    def _segundos_brutos_dia(self) -> int:
        if not self.hora_entrada or not self.hora_saida:
            return 0
        base = date(2000, 1, 1)
        inicio = datetime.combine(base, self.hora_entrada)
        fim = datetime.combine(base, self.hora_saida)
        return max(0, int((fim - inicio).total_seconds()))

    def trabalha_no_dia(self, dia: date) -> bool:
        mapa = {
            0: self.trabalha_segunda,
            1: self.trabalha_terca,
            2: self.trabalha_quarta,
            3: self.trabalha_quinta,
            4: self.trabalha_sexta,
        }
        return bool(mapa.get(dia.weekday(), False))

    def jornada_diaria_segundos(self) -> int:
        """Jornada líquida esperada num dia de trabalho."""
        bruto = self._segundos_brutos_dia()
        intervalo = int(self.intervalo_almoco_minutos or 0) * 60
        return max(0, bruto - intervalo)

    def jornada_diaria_horas(self) -> Decimal:
        return (Decimal(self.jornada_diaria_segundos()) / Decimal(3600)).quantize(
            Decimal("0.01")
        )

    def dias_trabalho_no_periodo(self, inicio: date, fim: date) -> int:
        if fim < inicio:
            return 0
        total = 0
        cursor = inicio
        while cursor <= fim:
            if self.trabalha_no_dia(cursor):
                total += 1
            cursor += timedelta(days=1)
        return total

    def segundos_previstos_periodo(self, inicio: date, fim: date) -> int:
        return self.dias_trabalho_no_periodo(inicio, fim) * self.jornada_diaria_segundos()

    def resumo_jornada(self) -> str:
        dias = [
            rotulo
            for _wd, campo, rotulo in DIAS_JORNADA
            if getattr(self, campo)
        ]
        if not dias:
            return "Sem dias de trabalho definidos"
        dias_txt = ", ".join(dias)
        entrada = self.hora_entrada.strftime("%H:%M")
        saida = self.hora_saida.strftime("%H:%M")
        liquida = self.jornada_diaria_horas()
        return f"{dias_txt} · {entrada}–{saida} ({liquida}h líquidas/dia)"


class AcessoModulo(Funcionario):
    """Visão do admin: matriz funcionário × módulo."""

    class Meta:
        proxy = True
        verbose_name = "Acesso aos módulos"
        verbose_name_plural = "Acessos aos módulos"
