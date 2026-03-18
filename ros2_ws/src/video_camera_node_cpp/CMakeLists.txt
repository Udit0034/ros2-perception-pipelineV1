cmake_minimum_required(VERSION 3.8)
project(video_camera_node_cpp)

# Use C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ── Find dependencies ──────────────────────────────────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(OpenCV REQUIRED)

# ── Build the node ─────────────────────────────────────────────────────────
add_executable(video_camera_node src/video_camera_node.cpp)

ament_target_dependencies(video_camera_node
  rclcpp
  sensor_msgs
  cv_bridge
  image_transport
  OpenCV
)

# ── Install ────────────────────────────────────────────────────────────────
install(TARGETS video_camera_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
