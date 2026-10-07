FROM python:3.12-slim AS base

# The pricing cache is the only state the collector keeps. Mounting it as a volume
# turns a cold start from a few hundred throttled Pricing API calls into zero.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COSTLENS_CACHE=/var/cache/costlens

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY costlens/ ./costlens/
COPY pyproject.toml .
RUN pip install --no-cache-dir --no-deps -e .

RUN useradd --system --uid 10001 costlens \
    && mkdir -p "$COSTLENS_CACHE" \
    && chown costlens:costlens "$COSTLENS_CACHE"
USER costlens

EXPOSE 9101

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:9101/metrics', timeout=4).status==200 else 1)"

ENTRYPOINT ["costlens"]
CMD ["run", "-c", "/etc/costlens/config.yaml"]
