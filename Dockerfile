# Imagem única do Mundo Vivo: a simulação + a API/WebSocket + a ponte MQTT,
# num processo só (python -m server). Ver docs/arquitetura.md, seção 1.1.
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
# (A cópia abaixo só vale se alguém rodar a imagem sem o volume.)
COPY data ./data
COPY viewer ./viewer
VOLUME ["/app/var"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Fase 4: simulação + servidor. Para só o terminal (Fases 1-3): python -m tools.run
CMD ["python", "-m", "server", "--porta", "8000"]
