from funcionarios.models import Cargo, Funcionario


CARGOS_DIRIGEM = {Cargo.GERENTE, Cargo.SOCIO, Cargo.SUPERVISOR}


def pode_dirigir_atividades(funcionario: Funcionario | None) -> bool:
    """Gerente, sócio ou supervisor podem direcionar atividades a outros."""
    if funcionario is None:
        return False
    return funcionario.cargo in CARGOS_DIRIGEM


def pode_gerenciar_atividade(
    funcionario: Funcionario | None,
    atividade,
) -> bool:
    if funcionario is None:
        return False
    if atividade.responsavel_id == funcionario.id:
        return True
    if atividade.criado_por_id == funcionario.id:
        return True
    if getattr(atividade, "pk", None) and atividade.participantes.filter(
        pk=funcionario.id
    ).exists():
        return True
    return pode_dirigir_atividades(funcionario)


def funcionarios_atribuiveis(ator: Funcionario):
    """Quem o ator pode escolher como responsável principal."""
    qs = Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
    if pode_dirigir_atividades(ator):
        return qs
    return qs.filter(pk=ator.pk)


def funcionarios_para_equipe(ator: Funcionario):
    """Colegas que podem entrar na equipe da atividade."""
    return Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
