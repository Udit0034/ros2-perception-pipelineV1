# syntax=docker/dockerfile:1.4
# =============================================================================
# Dockerfile — ROS2 Humble + PyTorch (CUDA) perception pipeline
#
# Build:   docker compose build
# Run:     docker compose up
# =============================================================================

FROM ros:humble

ENV DEBIAN_FRONTEND=noninteractive

# ── Install system dependencies (cached if possible) ─────────────────────────
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends \
      python3-pip \
      python3-opencv \
      ros-humble-cv-bridge \
      ros-humble-image-transport \
      libopencv-dev \
      libgl1-mesa-glx \
      libgtk2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Install PyTorch with CUDA support (cached across builds) ───────────────
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
      torch torchvision --index-url https://download.pytorch.org/whl/cu121

# ── Copy and build the ROS2 workspace ───────────────────────────────────────
WORKDIR /ros2_ws
COPY ros2_ws/src src/

RUN /bin/bash -c "\
    source /opt/ros/humble/setup.bash && \
    colcon build --symlink-install"

# ── Entrypoint ──────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "perception_launch", "perception_pipeline.launch.py", \
    "frames_dir:=/data/frames", \
    "label_dir:=/data/labels", \
    "model_path:=/data/segmentation_model_camvid.pt", \
    "class_dict_path:=/data/label_colors.csv"]
