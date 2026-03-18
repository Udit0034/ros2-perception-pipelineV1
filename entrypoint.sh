#!/bin/bash
# =============================================================================
# Entrypoint — sources ROS2 and the workspace, then runs the given command.
# =============================================================================
set -e

source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

exec "$@"
