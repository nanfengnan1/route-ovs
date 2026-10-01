VPCS 测试终端
========================================

当前接口
----------------------------------------

``script/frr_vpcs.py`` 是独立 Python 入口。它创建或复用 PC 容器，
通过一对 veth 直连目标容器和 PC 的空闲接口名。
本节以该脚本实际参数为准，不假定 ``frr_init.sh`` 已集成 VPCS 菜单。

从项目根目录查看帮助::

  python3 script/frr_vpcs.py --help
  python3 script/frr_vpcs.py --state-file script/.frr_vpcs.json add --help

创建连接
----------------------------------------

确认 ``frr_A`` 正常运行、两端接口名未占用，且本地已有 PC 镜像::

  python3 script/frr_vpcs.py \
    --state-file script/.frr_vpcs.json \
    --image alpine/vpcs:latest \
    add frr_A eth1 pc_A eth0

位置参数顺序为“目标容器、目标接口、PC 容器、PC 接口”。
目标容器和 PC 必须使用不同网络命名空间，工具拒绝向 host 网络容器接入接口。
创建 PC 时要求镜像已经存在，不会自动拉取镜像。

地址与连通性
----------------------------------------

连接成功不等于已配置 IP。先查看接口，再按实验地址表配置静态地址或 DHCP 客户端::

  docker exec pc_A ip addr
  docker exec frr_A ip addr

地址规划、DHCP 服务端配置和连通性验证用例：待补充。

删除连接
----------------------------------------

删除指定 PC 接口对应的连接::

  python3 script/frr_vpcs.py \
    --state-file script/.frr_vpcs.json delete pc_A eth0

清理该状态文件记录的全部连接::

  python3 script/frr_vpcs.py \
    --state-file script/.frr_vpcs.json delete-all

工具会核对容器和接口归属；自行创建的 PC 与复用的已有容器采用不同的回收规则。
报错时保留状态文件，按提示处理未完成的清理，再重试。
