# CamVid Semantic Segmentation — ROS2 Perception Pipeline

## Project Structure

```
Camera Sementic segmentation/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── .dockerignore
├── segmentation_model_camvid.pt   ← from Kaggle training
├── label_colors.csv               ← Carla label colours (used for runtime)
├── test.mp4                       ← your test video
└── ros2_ws/
    └── src/
        ├── video_camera_node_cpp/     # C++ — reads test.mp4 → /camera/image_raw
        ├── segmentation_node_py/      # Python — TorchScript DeepLabV3 inference
        ├── drivable_area_node_cpp/    # C++ — binary drivable mask
        └── perception_launch/         # Launch file to start everything
```

## Pipeline

```
test.mp4
  ↓
video_camera_node_cpp        → /camera/image_raw
  ↓
segmentation_node_py         → /perception/segmentation  →  [Segmentation window]
  ↓
drivable_area_node_cpp       → /perception/drivable_area →  [Drivable Area window]
  ↓
Video ends → all nodes shut down gracefully
```

## What happens when you run it

1. Two OpenCV windows open automatically:
   - **Segmentation** — original video blended with colored semantic segmentation
   - **Drivable Area** — binary mask showing only drivable regions (white)
2. Both windows update in real-time as the video plays (~10 FPS)
3. When the video finishes, all nodes shut down cleanly (no crash)

---

## Run with Docker (recommended)

### Prerequisites

- **Docker** with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- An **X11 display** for GUI windows:
  - **Linux:** works natively
  - **Windows 11 (WSL2):** WSLg provides X11 automatically
  - **Windows 10 (WSL2):** install [VcXsrv](https://sourceforge.net/projects/vcxsrv/) and run it with "Disable access control" checked

### Required files in the project root

Make sure these exist next to the `Dockerfile`:
- `segmentation_model_camvid.pt`
- `label_colors.csv` (or `class_dict.csv` if using CamVid training colors)
- `test.mp4`

### Build & run

**Linux:**
```bash
# Allow Docker to access your display
xhost +local:docker

# Build and run
docker compose build
docker compose up
```

**Windows (WSL2 terminal):**
```bash
# If using WSLg (Windows 11), display is automatic.
# If using VcXsrv, set:
export DISPLAY=host.docker.internal:0

docker compose build
docker compose up
```

### Stop

Press `Ctrl+C` — the container exits cleanly.

To remove the container:
```bash
docker compose down
```

---

## Run without Docker (native ROS2)

### Prerequisites

- **ROS2 Humble** (or later)
- **OpenCV**, **cv_bridge** (bundled with ROS2)
- **PyTorch** with CUDA support: `pip install torch torchvision`

### Build

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### Launch all nodes

```bash
ros2 launch perception_launch perception_pipeline.launch.py \
  video_path:=/absolute/path/to/test.mp4 \
  model_path:=/absolute/path/to/segmentation_model_camvid.pt \
  class_dict_path:=/absolute/path/to/label_colors.csv
```

### Or run nodes individually (3 terminals)

**Terminal 1 — Video camera:**
```bash
ros2 run video_camera_node_cpp video_camera_node \
    --ros-args -p video_path:=/absolute/path/to/test.mp4
```

**Terminal 2 — Segmentation:**
```bash
ros2 run segmentation_node_py segmentation_node \
  --ros-args \
  -p model_path:=/absolute/path/to/segmentation_model_camvid.pt \
  -p class_dict_path:=/absolute/path/to/label_colors.csv
```

**Terminal 3 — Drivable area:**
```bash
ros2 run drivable_area_node_cpp drivable_area_node
```

## Topics

| Topic | Type | Description |
|---|---|---|
| `/camera/image_raw` | `sensor_msgs/Image` (bgr8) | Raw video frames |
| `/perception/segmentation` | `sensor_msgs/Image` (bgr8) | Colored segmentation mask |
| `/perception/drivable_area` | `sensor_msgs/Image` (mono8) | Binary drivable area mask |
