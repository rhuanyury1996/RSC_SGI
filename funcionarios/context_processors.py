from .utils import obter_funcionario


def colaborador(request):
    return {"colaborador": obter_funcionario(request)}
