# Repository Guidelines

## Project Structure & Module Organization

本仓库是 ROS2 `ament_cmake` 工作区。核心节点位于 `src/linker_hand_cpp_ros2/`，入口源码为 `src/linker_hand_cpp_ros2/src/linker_hand_node.cpp`，启动文件在 `src/linker_hand_cpp_ros2/launch/run.xml`。示例程序位于 `src/examples/src/`，每个 `.cpp` 文件对应一个独立可执行示例。包元数据和构建规则分别由各包内的 `package.xml` 与 `CMakeLists.txt` 管理。仓库根目录保留 `README.md`、`LICENSE` 和本指南。

## Build, Test, and Development Commands

- `colcon build`: 从仓库根目录构建全部 ROS2 包。
- `colcon build --packages-select linker_hand_cpp_ros2`: 仅构建核心节点包，适合快速验证节点改动。
- `source install/setup.bash`: 加载构建后的工作区环境。
- `ros2 launch linkerhand_cpp_ros2 run.xml`: 启动 LinkerHand ROS2 节点。
- `colcon test`: 运行已启用的 ROS2/ament 测试与 lint 钩子。
- `colcon test-result --verbose`: 查看测试失败详情。

构建前需确保已安装 ROS2 Foxy 或 Humble，以及兼容的 `linkerhand-cpp-sdk`（README 标注支持 v1.1.7 及以下）。

## Coding Style & Naming Conventions

项目使用 C++14，CMake 中启用 `-Wall -Wextra -Wpedantic`。遵循现有代码风格：CMake 变量使用大写或描述性蛇形命名，C++ 文件和 ROS2 可执行目标使用小写下划线，例如 `show_wave_l20.cpp`。新增示例应放入 `src/examples/src/`，并同步更新 `src/examples/CMakeLists.txt` 的 `SOURCE_FILES`。注释只解释非显然原因，避免描述代码表面行为。

## Testing Guidelines

当前未包含专门的单元测试目录，主要依赖 `colcon build`、`colcon test` 与运行验证。涉及节点行为的改动，应至少构建核心包，并在可用硬件或仿真环境下运行 `ros2 launch linkerhand_cpp_ros2 run.xml`。新增测试时优先使用 ROS2/ament 生态，并保持测试名称与目标功能对应。

## Commit & Pull Request Guidelines

Git 历史使用英文前缀提交信息，例如 `docs: update README`、`feat: update ci/cd`。提交应采用 `type: 简短说明` 格式，常用类型包括 `feat`、`fix`、`docs`、`build`、`test`、`refactor`。Pull Request 应说明变更目的、影响范围、验证命令和结果；涉及硬件行为时注明设备型号、CAN 口配置和是否完成实机验证。

## Security & Configuration Tips

不要提交本地构建产物、硬件私有配置或凭据。修改 `run.xml` 默认参数时，确认左右手存在性、型号、触觉开关和 CAN 设备名与 README 中的话题约定一致。
