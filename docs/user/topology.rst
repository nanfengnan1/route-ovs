拓扑与抓包
========================================

OVS 链路规划
----------------------------------------

每个实验应记录网桥名、两端容器名、接口名、VLAN 和 IP 地址。
当前拓扑采集器通过 ``ovs-docker`` 风格的 ``external_ids`` 识别容器接口，
不能只根据端口显示名称推断连接。

可先查看宿主机的网桥和端口::

  sudo ovs-vsctl show

网桥创建、端口接入、VLAN 和完整清理示例：待按实际实验补充。

生成拓扑图
----------------------------------------

在保存 ``.frr_containers.tmp`` 的 ``script/`` 目录执行::

  bash frr_init.sh -g ./topology.svg

也可以在项目根目录显式指定输入和输出::

  python3 script/frr_topology.py \
    --containers-file script/.frr_containers.tmp \
    --output ./topology.svg

输出目录必须已存在，文件后缀必须为 ``.svg``。采集过程只读取 Docker、
容器接口和 OVS 状态；图中内容是采集时的快照，不会持续刷新。
应同时检查命令输出的警告，不能把缺失的连线直接认定为业务断链。

抓取容器接口报文
----------------------------------------

假设实验已创建 ``frr_A`` 的 ``eth1`` 接口，在 ``script/`` 目录执行::

  bash frr_init.sh -t frr_A eth1

脚本调用宿主机的 ``tcpdump``，通过 ``nsenter`` 进入容器网络命名空间。
按 Ctrl+C 停止。无需为了该入口在 FRR 镜像中额外安装 tcpdump。

拓扑输出格式、报文字段和实验结果归档规范可在后续实验章节中补充。
