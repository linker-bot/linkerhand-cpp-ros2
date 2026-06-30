# LinkerHand-CPP-ROS2

[![CI/CD Pipeline](https://github.com/linker-bot/linkerhand-cpp-ros2/actions/workflows/ci.yml/badge.svg)](https://github.com/linker-bot/linkerhand-cpp-ros2/actions/workflows/ci.yml)
[![ROS2 Version](https://img.shields.io/badge/ROS2-Foxy-blue.svg)](https://docs.ros.org/en/foxy/index.html)
[![ROS2 Version](https://img.shields.io/badge/ROS2-Humble-blue.svg)](https://docs.ros.org/en/humble/index.html)
[![License](https://img.shields.io/badge/License-Apache%202.0-orange.svg)](LICENSE)


## 概述
LinkerHand-CPP-ROS2 是灵心巧手科技有限公司开发，基于 LinkerHand-CPP-SDK 的ROS2封装版本。


## 📋 目录

- [环境要求](#-环境要求)
- [快速开始](#-快速开始)
- [话题详情](#-话题详情)
- [使用示例](#-使用示例)
- [许可证](#-许可证)
- [联系我们](#-联系我们)
- [更新日志](#-更新日志)

## 💻 环境要求

- **操作系统**: Linux (Ubuntu 20.04+ 推荐)
- **架构**: x86_64
- **编译器**: GCC 7.0+ 或 Clang 6.0+（C++17）
- **CMake**: 3.15+
- **依赖**: ROS2 (推荐 Foxy 或 Humble)、[linkerhand-cpp-sdk v2.1.7](https://github.com/linker-bot/linkerhand-cpp-sdk/releases/tag/v2.1.7)

> 注：本项目已适配 linkerhand-cpp-sdk v2.1.7；O20 依赖 CAN-FD，当前 ROS2 节点仍以普通 CAN 为主，暂未完成 O20 实机运行适配。


## 🚀 快速开始
#### 下载
    git clone https://github.com/linker-bot/linkerhand-cpp-ros2.git

#### 编译
    cd linkerhand-cpp-ros2/
    colcon build

#### 配置XML文件

```bash
<?xml version="1.0" encoding="utf-8"?>
<launch>
  <!-- 参数声明 -->
  <arg name="VERSION" default="2.1.7" description="SDK版本号"/>

  <!-- 左手配置 -->
  <arg name="LEFT_HAND_EXISTS" default="true" description="是否存在左手"/>
  <arg name="LEFT_TOUCH" default="true" description="是否有压力传感器"/>
  <arg name="LEFT_JOINTS" default="L10" description="左手型号 L6 \ L7 \ L10 \ L20 \ L21 \ L25 \ O6 \ O20 \ G20"/>
  <arg name="LEFT_CANBUS" default="can0" description="can0 \ can1"/>

  <!-- 右手配置 -->
  <arg name="RIGHT_HAND_EXISTS" default="false" description="是否存在右手"/>
  <arg name="RIGHT_TOUCH" default="false" description="是否有压力传感器"/>
  <arg name="RIGHT_JOINTS" default="L10" description="右手型号 L6 \ L7 \ L10 \ L20 \ L21 \ L25 \ O6 \ O20 \ G20"/>
  <arg name="RIGHT_CANBUS" default="can0" description="can0 \ can1"/>

  <!-- 通用配置 -->
  <arg name="HAND_SPEED" default="100" description="关节速度 0 ~ 255"/>
  <arg name="HAND_EFFORT" default="200" description="关节扭矩 0 ~ 255"/>
  <arg name="CAN_BITRATE" default="1000000" description="CAN波特率"/>

  ......
  
</launch>
```

#### 运行
    source install/setup.bash
    ros2 launch linker_hand_cpp_ros2 run.xml


## 📚 话题详情

| 话题名称 | I/O | 消息类型 | 描述 |
| :--- | :--- | :--- | :--- |
| /left_hand_control | Input | sensor_msgs/msg/JointState | 左手控制指令 |
| /left_hand_settings | Input | sensor_msgs/msg/String | 左手设置指令 |
| /left_hand_touch | Output | std_msgs/msg/Float32MultiArray | 左手触觉传感器数据 |
| /left_hand_state | Output | sensor_msgs/msg/JointState | 左手关节状态 |
| /left_hand_info | Output | std_msgs/msg/String | 左手基本信息 |
| /right_hand_control | Input | sensor_msgs/msg/JointState | 左手控制指令 |
| /right_hand_settings | Input | sensor_msgs/msg/String | 右手设置指令 |
| /right_hand_touch | Output | std_msgs/msg/Float32MultiArray | 左手触觉传感器数据 |
| /right_hand_state | Output | sensor_msgs/msg/JointState | 左手关节状态 |
| /right_hand_info | Output | std_msgs/msg/String | 左手基本信息 |


针对以上话题的具体字段及其详细描述如下表所示：


- 控制关节话题 /left_hand_control

```bash
  $ ros2 topic echo /left_hand_control

  header: 
    seq: 256
    stamp: 
      secs: 1744343699
      nsecs: 232647418
    frame_id: ''
  name: []
  position: [155.0, 162.0, 176.0, 125.0, 255.0, 255.0, 180.0, 179.0, 181.0, 68.0]
  velocity: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  effort: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```
- position与手指关节对照表

```bash
L7:  ["大拇指弯曲", "大拇指横摆","食指弯曲", "中指弯曲", "无名指弯曲","小拇指弯曲","拇指旋转"]

L6/O6:  ["拇指根部", "拇指侧摆", "食指根部", "中指根部", "无名指根部", "小指根部"]

L10: ["拇指根部", "拇指侧摆","食指根部", "中指根部", "无名指根部","小指根部","食指侧摆","无名指侧摆","小指侧摆","拇指旋转"]

L20: ["拇指根部", "食指根部", "中指根部", "无名指根部","小指根部","拇指侧摆","食指侧摆","中指侧摆","无名指侧摆","小指侧摆","拇指横摆","预留","预留","预留","预留","拇指尖部","食指末端","中指末端","无名指末端","小指末端"]

G20: ["大拇指根部", "食指根部", "中指根部","无名指根部","小拇指根部","大拇指侧摆","食指侧摆","中指侧摆","无名指侧摆","小拇指侧摆","大拇指横滚","大拇指指尖","食指指尖","中指指尖","无名指指尖","小拇指指尖"]

L21: ["大拇指根部", "食指根部", "中指根部","无名指根部","小拇指根部","大拇指侧摆","食指侧摆","中指侧摆","无名指侧摆","小拇指侧摆","大拇指横滚","预留","预留","预留","预留","大拇指中部","预留","预留","预留","预留","大拇指指尖"]

L25: ["大拇指根部", "食指根部", "中指根部","无名指根部","小拇指根部","大拇指侧摆","食指侧摆","中指侧摆","无名指侧摆","小拇指侧摆","大拇指横滚","预留","预留","预留","预留","大拇指中部","食指中部","中指中部","无名指中部","小拇指中部","大拇指指尖","食指指尖","中指指尖","无名指指尖","小拇指指尖"]
```


---


- 设置指令话题 /left_hand_settings

```bash
  # 清除故障码
  $ ros2 topic pub /left_hand_setting std_msgs/msg/String "data: '{\"setting_cmd\": \"clear_faults\"}'"

  # 设置电流（linkerhand-cpp-sdk v2.1.7 暂不支持，节点会输出警告）
  $ ros2 topic pub /left_hand_setting std_msgs/msg/String "data: '{\"setting_cmd\": \"set_electric_current\", \"params\": {\"electric_current\": 50}}'"

  # 使能
  $ ros2 topic pub /left_hand_setting std_msgs/msg/String "data: '{\"setting_cmd\": \"enable\"}'"

  # 失能
  $ ros2 topic pub /left_hand_setting std_msgs/msg/String "data: '{\"setting_cmd\": \"disable\"}'"

```


---
- 关节反馈话题 /left_hand_state

```bash
 $ ros2 topic echo /left_hand_state

  header: 
    seq: 256
    stamp: 
      secs: 1744343699
      nsecs: 232647418
    frame_id: ''
  name: []
  position: [155.0, 162.0, 176.0, 125.0, 255.0, 255.0, 180.0, 179.0, 181.0, 68.0]
  velocity: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  effort: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

---

- 左手基本信息 /left_hand_info

```bash
$ ros2 topic echo /left_hand_info

data: 'Hand direction: Left hand

  Software Version: 7.0.0.0

  Hardware Version: 2.0.19.0

  Temperature: 47 49 40 41 0 39 0 46 42 0 0 39 0 49...'
```
- 压感数据 /left_hand_touch

  注意：反馈数据为一个一维数组，长度为360，由每个手指的压感数据组成。单个指头压感数据长度是72（6*12矩阵），每个手指压感数据需要单独拆分。（仅适用点阵式传感器）

```bash
$ ros2 topic echo /left_hand_touch 
layout:
  dim: []
  data_offset: 0
data:
- 0.0
- 0.0
- 0.0
- 0.0
- 0.0
- '...'
```

## 📄 许可证

本项目采用 [Apache 2.0 许可证](LICENSE)。

Copyright (c) 2026 灵心巧手（北京）科技有限公司

## 📞 联系我们

- **官方网站**: [https://linkerbot.cn](https://linkerbot.cn)
- **关于我们**: [https://linkerbot.cn/aboutUs](https://linkerbot.cn/aboutUs)
- **GitHub**: [https://github.com/linker-bot/linkerhand-cpp-ros2](https://github.com/linker-bot/linkerhand-cpp-ros2)

## 📝 更新日志

详细的版本更新记录请参考 [CHANGELOG.md](CHANGELOG.md)（待创建）。

---

**注意**: 使用前请确保设备已正确连接并配置好通信接口。
