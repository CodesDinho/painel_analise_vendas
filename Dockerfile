FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

RUN apt-get update \
    && apt-get install --no-install-recommends -y libfbclient2 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 painel

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=painel:painel . .
RUN mkdir -p cache temporarios dados_locais relatorios credentials config_runtime \
    && chown -R painel:painel /app

USER painel
EXPOSE 8520

CMD ["python", "-m", "streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8520", "--server.headless=true"]
