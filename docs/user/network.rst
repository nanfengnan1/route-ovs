网络配置
========================================

本章介绍实验接口的网络参数配置。以下以 route 容器 ``frr_A`` 和
VPCS 容器 ``pc_A`` 为例，容器名和接口名应按实际拓扑替换。

DHCP
----------------------------------------

本项目的 VPCS 是 Alpine Linux 测试容器，route 容器使用 ``dnsmasq`` 提供 DHCP 服务。
客户端程序名应以实际镜像为准：本机 ``alpine/vpcs:latest`` 提供 ``dhcpcd``；
如果使用已安装 ``dhcpd`` 客户端入口的环境，启动命令见下文。

实验拓扑与准备
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

先按 :doc:`vpcs` 接入测试终端，确认链路已经建立。本例使用以下地址规划：

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - 角色
     - 容器与接口
     - 地址或参数
   * - route / DHCP 服务端
     - ``frr_A eth1``
     - ``192.168.100.1/24``
   * - VPCS / DHCP 客户端
     - ``pc_A eth0``
     - 通过 DHCP 自动获取 IPv4 地址
   * - DHCP 地址池
     - ``192.168.100.0/24``
     - ``192.168.100.100`` 至 ``192.168.100.200``，租期 1 小时
   * - 默认网关
     - DHCP option 3
     - ``192.168.100.1``
   * - DNS
     - DHCP option 6
     - 本例不下发 DNS 服务器地址

链路示意::

  pc_A eth0（DHCP 客户端） -------- frr_A eth1（192.168.100.1/24）

两端应处于同一二层广播域；经过 OVS 时需接入同一 VLAN。
本例不使用 DHCP relay。实验接口应为专用接口，避免与已有静态地址或其他
DHCP 客户端配置冲突，同一广播域中也不应有非预期的 DHCP 服务端。

以下 ``docker exec`` 命令在宿主机执行。进入容器后，以 root 身份配置接口。
先检查软件是否可用::

  docker exec pc_A dhcpcd --version
  docker exec frr_A dnsmasq --version

项目的 VPCS Dockerfile 已安装 ``dhcpcd``，route Dockerfile 的最终运行阶段
已安装 ``dnsmasq`` 和 ``iproute2``。使用旧镜像或其他镜像时，应以检查结果为准。
若 Alpine 容器缺少软件，可在宿主机按需安装::

  docker exec -u 0 pc_A apk add --no-cache dhcpcd iproute2 iputils
  docker exec -u 0 frr_A apk add --no-cache dnsmasq iproute2

容器内安装只影响当前容器；重建时应使用包含这些软件的镜像。

route 配置 DHCP 服务端
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在宿主机终端 1 进入 route 容器::

  docker exec -u 0 -it frr_A sh

在 route 容器中启用接口并配置网关地址::

  ip link set dev eth1 up
  ip addr replace 192.168.100.1/24 dev eth1
  ip -4 addr show dev eth1

然后在同一容器中启动 dnsmasq::

  dnsmasq -d -C /dev/null -i eth1 -p 0 \
    --dhcp-range=192.168.100.100,192.168.100.200,1h \
    --dhcp-option=3,192.168.100.1 \
    --dhcp-option=6

参数说明：

* ``-d``：前台运行并输出调试日志；保留该终端，按 Ctrl+C 停止服务。
* ``-C /dev/null``：使用空配置文件，不读取默认的 ``/etc/dnsmasq.conf``。
* ``-i eth1``：在实验接口 ``eth1`` 上提供服务。
* ``-p 0``：关闭 DNS 监听，保留 DHCP 功能。
* ``--dhcp-range``：设置地址池和租期；本例未显式写掩码，
  dnsmasq 根据已配置的 ``eth1`` 地址确定 ``/24`` 子网。
* ``--dhcp-option=3,192.168.100.1``：向客户端下发默认网关。
* ``--dhcp-option=6``：不下发 DNS 服务器选项；不会清除客户端已有的 DNS 配置。
  如需下发 DNS，应将其替换为 ``--dhcp-option=6,<实际可达的DNS服务器IP>``。
  本例关闭了 DNS 监听，因此不要把 ``192.168.100.1`` 当作本例提供的 DNS 服务。

选项行为参见 `dnsmasq 官方手册 <https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html>`_。

DHCP 下发网关不会自动开启路由转发。访问其他网段还需配置 route 的 IPv4 转发、
路由、回程路径及相应的防火墙规则；本例先验证客户端到网关的连通性。

VPCS 配置 DHCP 客户端
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

保持服务端运行，在宿主机终端 2 进入 VPCS 容器::

  docker exec -u 0 -it pc_A sh

**使用现有环境中的 dhcpd 客户端入口**

如果已经确认该环境中的 ``dhcpd`` 是 DHCP 客户端，按现有启动方式执行::

  ip link set dev eth0 up
  dhcpd eth0

``dhcpd`` 在常见发行版中也用作 DHCP 服务端的程序名，因此仅适用于已确认提供
该客户端入口的环境。可用 ``command -v dhcpd`` 和 ``dhcpd --help`` 核对路径及用途，
不要把不同 DHCP 软件的参数混用。

**使用仓库提供的 VPCS 镜像**

当前 ``docker/devices/vpcs/Dockerfile`` 安装的是 ``dhcpcd``。
已核对本机 ``alpine/vpcs:latest`` 中存在 ``/sbin/dhcpcd``（版本 10.5.2），
未提供 ``dhcpd``。使用该镜像时，在 VPCS 容器中执行::

  ip link set dev eth0 up
  dhcpcd -4 eth0

``-4`` 表示仅配置 IPv4，``eth0`` 限定申请地址的接口。
成功获取租约后，dhcpcd 在后台继续维护租约。不要同时在该接口运行其他 DHCP 客户端。
这是一组 Linux 容器命令，不是 GNS3 VPCS 模拟终端的 ``ip dhcp`` 命令。

验证地址、路由与租约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

无论使用哪个客户端，都可以在 VPCS 容器中检查地址和连通性::

  ip -4 addr show dev eth0
  ip -4 route show
  ping -c 4 192.168.100.1

确认 ``eth0`` 获得地址池内的 ``/24`` 地址、默认路由包含
``default via 192.168.100.1 dev eth0``，并能 ping 通网关。
出现 ``169.254.x.x`` 链路本地地址不能视为从本例服务器获取地址成功。

使用 dhcpcd 时，还可以显示保存的 IPv4 租约信息::

  dhcpcd -4 -U eth0

服务端终端可观察 DHCP 请求与应答日志。新租约通常经历
DHCPDISCOVER、DHCPOFFER、DHCPREQUEST、DHCPACK；续租或复用租约时日志可能不同。
需要抓包时，在宿主机另一个终端执行::

  docker exec -u 0 pc_A tcpdump -ni eth0 -vv 'udp port 67 or udp port 68'

获取失败时，先核对接口名、链路状态、route 的 ``192.168.100.1/24`` 地址及
dnsmasq 进程是否仍运行，再检查两端的二层连通性、VLAN 和 DHCP UDP 67/68 端口过滤。

重新申请与结束实验
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以下租约管理参数针对 ``dhcpcd``；若使用 ``dhcpd`` 客户端入口，应按其实际实现的
帮助说明操作。dhcpcd 已经运行时，可在 VPCS 容器中重新读取配置并请求绑定::

  dhcpcd -4 -n eth0

需要释放地址并停止本例客户端时，在 VPCS 容器中执行::

  dhcpcd -4 -k eth0

若要再次申请，重新执行 ``dhcpcd -4 eth0``。
这些操作应保持与启动命令相同的 ``-4`` 和接口名；
参数说明见 `dhcpcd 手册 <https://man.archlinux.org/man/dhcpcd.8.en>`_。

结束实验时先释放客户端租约，再在服务端终端按 Ctrl+C 停止 dnsmasq。
本节通过命令行配置接口并运行 DHCP 服务，未设置容器启动时自动恢复。
