from funcionarios.models import Cargo, Funcionario


CARGOS_DIRIGEM = {Cargo.GERENTE, Cargo.SOCIO, Cargo.SUPERVISOR}


def pode_dirigir_atividades(funcionario: Funcionario | None) -> bool:
    """Gerente, sócio, supervisor ou admin podem direcionar atividades a outros."""
    if funcionario is None:
        return False
    if funcionario.cargo in CARGOS_DIRIGEM:
        return True
    usuario = getattr(funcionario, "usuario", None)
    return bool(usuario and (usuario.is_staff or usuario.is_superuser))


def pode_gerenciar_atividade(
    funcionario: Funcionario | None,
    atividade,
) -> bool:
    """Responsável, participantes e gestores/admin editam e excluem."""
    if funcionario is None:
        return False
    if atividade.responsavel_id == funcionario.id:
        return True
    if getattr(atividade, "pk", None) and atividade.participantes.filter(
        pk=funcionario.id
    ).exists():
        return True
    return pode_dirigir_atividades(funcionario)


def pode_alterar_status(funcionario: Funcionario | None, atividade) -> bool:
    """Edição completa, ou marcar subtarefa atribuída à própria pessoa."""
    if pode_gerenciar_atividade(funcionario, atividade):
        return True
    if funcionario is None or not getattr(atividade, "atividade_pai_id", None):
        return False
    return atividade.faz_parte_da_equipe(funcionario)


def pode_comentar_atividade(funcionario: Funcionario | None, atividade) -> bool:
    return funcionario is not None and getattr(atividade, "pk", None)


def funcionarios_atribuiveis(ator: Funcionario):
    """Quem o ator pode escolher como responsável principal."""
    qs = Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
    if pode_dirigir_atividades(ator):
        return qs
    return qs.filter(pk=ator.pk)


def funcionarios_para_equipe(ator: Funcionario):
    """Colegas que podem entrar na equipe da atividade."""
    return Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
