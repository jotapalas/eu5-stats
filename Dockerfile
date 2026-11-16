FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3

# DEV=1 also installs the test dependencies (requirements-dev.txt).
ARG DEV=0
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$DEV" = "1" ]; then req=requirements-dev.txt; else req=requirements.txt; fi \
    && pip install --no-cache-dir -r "$req"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
