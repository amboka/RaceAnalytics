# ---------- Base: NVIDIA CUDA ----------
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

# ---------- System deps ----------
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

# ---------- ROS2 Humble ----------
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

# init rosdep
RUN rosdep init || true && rosdep update

# ---------- Python virtual environment ----------
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel

# Install project Python dependencies from requirements file.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---------- PyTorch (CUDA) ----------
RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# ---------- Jupyter + Python libs ----------
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

# ---------- Environment ----------
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

WORKDIR /workspace

EXPOSE 8888
EXPOSE 8000

CMD ["/bin/bash", "-lc", "source /opt/ros/humble/setup.bash && exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root"]
