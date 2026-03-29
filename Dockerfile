# syntax=docker/dockerfile:1.7

# ==========================================================
# RaceAnalytics unified Dockerfile
# Targets:
#   - backend
#   - frontend
#   - online
# ==========================================================

# ---------- Backend target (Django + ROS2 + CUDA) ----------
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS backend

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    lsb-release \
    build-essential \
    git \
    wget \
    python3-pip \
    python3-dev \
    python3-argcomplete \
    python3-venv \
    sqlite3 \
    libpq-dev \
    postgresql-client \
    nano \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg

RUN echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/ros2.list

RUN apt-get update && apt-get install -y \
    ros-humble-desktop-full \
    ros-humble-rosbag2 \
    ros-humble-rosbag2-storage-mcap \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init || true && rosdep update

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel

COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

RUN pip install --no-cache-dir \
    "numpy<2" \
    scipy \
    pandas \
    matplotlib \
    scikit-learn \
    notebook \
    jupyterlab \
    open3d \
    pypcd4

RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

WORKDIR /workspace/backend
COPY backend /workspace/backend

EXPOSE 8000 8888

CMD ["/bin/bash", "-lc", "source /opt/ros/humble/setup.bash && python manage.py runserver 0.0.0.0:8000"]


# ---------- Frontend target (Vite + React) ----------
FROM node:20-bookworm-slim AS frontend

WORKDIR /workspace/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend /workspace/frontend

EXPOSE 8080
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "8080"]


# ---------- Online target (Python co-driver) ----------
FROM python:3.11-slim AS online

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    CODRIVER_SKIP_PROMPT=1 \
    CODRIVER_TTS_BACKEND=espeak

WORKDIR /workspace/online

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

COPY online/requirements.txt /tmp/online-requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/online-requirements.txt

COPY online/files /workspace/online/files

WORKDIR /workspace/online/files

CMD ["python", "main.py", "--synthetic", "--no-claude", "--speed", "3.0"]
