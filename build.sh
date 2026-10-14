#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Cria/atualiza o CEO se CEO_PASSWORD estiver definido nas env vars do Render
if [ -n "${CEO_PASSWORD:-}" ]; then
  python manage.py bootstrap_ceo
fi

# Cadastra feriados nacionais (crédito automático de jornada)
python manage.py cadastrar_feriados
