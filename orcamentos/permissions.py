from funcionarios.models import Cargo, Funcionario

CARGOS_GESTAO = {Cargo.GERENTE, Cargo.SOCIO, Cargo.SUPERVISOR}


def pode_emitir_orcamento(funcionario: Funcionario | None) -> bool:
    """Qualquer colaborador ativo emite proposta."""
    return funcionario is not None


def pode_gerir_parametros(funcionario: Funcionario | None) -> bool:
    """Gerente, sócio, supervisor ou admin editam a tabela de preços."""
    if funcionario is None:
        return False
    if funcionario.cargo in CARGOS_GESTAO:
        return True
    usuario = getattr(funcionario, "usuario", None)
    return bool(usuario and (usuario.is_staff or usuario.is_superuser))


# Sobrescrever o sequencial do dia é a mesma alçada de editar os parâmetros.
pode_sobrescrever_sequencial = pode_gerir_parametros
