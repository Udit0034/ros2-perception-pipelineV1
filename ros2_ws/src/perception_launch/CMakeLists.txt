cmake_minimum_required(VERSION 3.8)
project(perception_launch)

find_package(ament_cmake REQUIRED)

# ── Install launch files ───────────────────────────────────────────────────
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

ament_package()
