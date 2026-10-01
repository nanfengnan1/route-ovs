环境准备
========================================

宿主机要求
----------------------------------------

使用能够运行 Linux 容器的 Linux 主机。现有工具按需使用以下命令：

* 容器管理：``docker``、``bash``、GNU ``getopt``。
* 网络操作：``ip``（iproute2）、``nsenter``；非 root 用户需要 ``sudo``。
* OVS 实验：``ovs-vsctl`` 和运行中的 OVS 服务。
* 抓包与拓扑：宿主机 ``tcpdump``、``python3``、Graphviz 的 ``dot``。

先核对环境::

  docker version
  ip -Version
  ovs-vsctl --version
  dot -V
  python3 --version

执行容器管理的用户需能访问 Docker；登记 netns 和操作 veth 时还需要宿主机网络管理权限。
发行版安装步骤、已验证的宿主机版本和资源基线：待补充。

准备镜像
----------------------------------------

项目已提供镜像归档，可以在项目根目录加载::

  docker load -i devices/route/frr.tar.xz
  docker load -i devices/vpcs/vpcs.tar.xz
  docker image ls

应以加载输出为准核对镜像标签。当前 ``script/frr_init.sh`` 中的
``CONTAINER_IMG`` 为 ``quay.io/frrouting/frr:10.0.0``；VPCS 工具默认使用
``alpine/vpcs:latest``。归档文件名不保证内部标签与上述默认值相同。

VPCS 镜像也可从项目中的 Dockerfile 构建，见开发指南“镜像构建”章节。
该镜像当前安装的是 DHCP 客户端 ``dhcpcd``，不是 DHCP 服务端。

实验目录
----------------------------------------

建议每个实验使用独立目录，保存容器清单、VPCS 状态、协议配置和采集结果。
由于 FRR 名称固定从 ``frr_A`` 开始，不同实验目录并不能避免同一 Docker 主机上的同名冲突。
