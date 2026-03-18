cmake_minimum_required(VERSION 3.8)
project(drivable_area_node_cpp)

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
add_executable(drivable_area_node src/drivable_area_node.cpp)

ament_target_dependencies(drivable_area_node
  rclcpp
  sensor_msgs
  cv_bridge
  image_transport
  OpenCV
)

# ── Install ────────────────────────────────────────────────────────────────
install(TARGETS drivable_area_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
