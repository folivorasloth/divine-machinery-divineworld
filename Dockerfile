# Imagem única da simulação (e, a partir da Fase 4, do servidor).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

WORKDIR /app
COPY pyproject.toml ./
COPY sim ./sim
COPY server ./server
COPY tools ./tools
RUN pip install --no-cache-dir .

# data/ e var/ entram como volumes (ver docker-compose.yml), para o João
# editar os YAML sem rebuild e para o SQLite sobreviver a reinícios.
COPY data ./data
VOLUME ["/app/var"]

# Fase 1: simulação headless em tempo real. A Fase 4 troca por
# `python -m server` (simulação + API no mesmo processo).
CMD ["python", "-m", "tools.run"]
