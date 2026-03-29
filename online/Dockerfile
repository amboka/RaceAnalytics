FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    CODRIVER_SKIP_PROMPT=1 \
    CODRIVER_TTS_BACKEND=espeak

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    espeak-ng \
    libasound2 \
    libespeak-ng1 \
    libespeak-ng-dev \
    libpulse0 \
    fonts-dejavu-core \
    pulseaudio-utils \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install -r requirements.txt

COPY files ./files

WORKDIR /app/files

CMD ["python", "main.py", "--synthetic", "--no-claude", "--speed", "3.0"]
