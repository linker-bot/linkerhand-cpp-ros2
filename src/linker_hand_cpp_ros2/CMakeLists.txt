cmake_minimum_required(VERSION 3.10)
project(linker_hand_cpp_ros2)

# Default to C99
if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()

# Default to C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(linkerhand-cpp-sdk 2.0 CONFIG REQUIRED)

add_executable(linker_hand_node src/linker_hand_node.cpp)
target_include_directories(linker_hand_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
ament_target_dependencies(linker_hand_node rclcpp std_msgs sensor_msgs)

target_link_libraries(linker_hand_node LinkerHand::linkerhand_cpp_sdk nlohmann_json::nlohmann_json)


install(TARGETS linker_hand_node
  DESTINATION lib/${PROJECT_NAME})

install(PROGRAMS
  scripts/hand_control_gui.py
  DESTINATION lib/${PROJECT_NAME}
)

install (DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

# install(DIRECTORY config
#   DESTINATION share/${PROJECT_NAME}
# )

# install(FILES config/setting.yaml
#   DESTINATION config
# )

set_target_properties(linker_hand_node PROPERTIES
  BUILD_RPATH "${linkerhand-cpp-sdk_LIBRARY_DIR}"
  INSTALL_RPATH "${linkerhand-cpp-sdk_LIBRARY_DIR}"
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  
  # 添加以下行来跳过风格和版权检查
  set(ament_cmake_xmllint_FOUND TRUE)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  set(ament_cmake_uncrustify_FOUND TRUE)
  set(ament_cmake_lint_cmake_FOUND TRUE)

  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
