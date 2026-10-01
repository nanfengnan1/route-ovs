工程结构
========================================

当前目录职责
----------------------------------------

.. code-block:: text

   route-ovs/
   ├── devices/
   │   ├── route/           # FRR 镜像归档
   │   ├── switch/          # 交换设备资源目录
   │   └── vpcs/            # 测试终端镜像归档
   ├── docker/devices/vpcs/ # VPCS 镜像 Dockerfile
   ├── protocols/bgp4/      # BGP IPv4 实验目录
   ├── script/
   │   ├── frr_init.sh      # FRR 容器、netns、抓包与拓扑入口
   │   ├── frr_topology.py  # 只读拓扑采集和 SVG 渲染
   │   └── frr_vpcs.py      # 专用 veth 直连和 VPCS 生命周期
   ├── tests/              # 现有脚本测试和 netns 集成检查
   └── docs/               # Sphinx 文档源码与构建入口

本框架依据当前工作区文件整理；部分脚本和测试可能尚未纳入 Git，
发布前应通过 ``git status`` 确认所依赖的文件已包含在交付版本中。

接口与数据
----------------------------------------

FRR 清单是逐行容器名；VPCS 使用带版本字段的 JSON 状态和文件锁。
拓扑采集器读取 Docker JSON、容器接口 JSON 和 OVS 表，再生成 Graphviz 描述与 SVG。

状态格式、模块间接口和错误处理约定见“脚本开发”章节，详细数据字段可随实现补充。
