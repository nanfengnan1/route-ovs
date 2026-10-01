快速开始
========================================

本节先验证容器和管理入口。业务链路、IP 地址以及路由协议需按实验拓扑另行配置。

创建 FRR 容器
----------------------------------------

完成 :doc:`deployment` 后，从项目根目录进入脚本目录，创建两个容器::

  cd script
  bash frr_init.sh --help
  bash frr_init.sh -n 2

脚本创建 ``frr_A``、``frr_B``，登记同名 netns，并启用和启动 ``ospfd``。
创建数量范围为 1 到 26。操作记录写入当前目录的 ``.frr_containers.tmp``。

查看运行状态
----------------------------------------

在同一工作目录执行::

  docker ps
  sudo ip netns list
  docker exec frr_A vtysh -c 'show version'
  docker exec frr_A vtysh -c 'show interface'

如果容器仍在运行，但缺少同名 netns 登记，可针对清单中的容器执行::

  bash frr_init.sh --netns

已有同名映射指向其他网络命名空间时，脚本会报错，应先核对映射归属。

后续操作
----------------------------------------

* 按 :doc:`topology` 规划 OVS 链路并采集拓扑。
* 按 :doc:`vpcs` 接入测试终端。
* 按 :doc:`protocols/index` 编写和执行具体协议实验。

结束实验
----------------------------------------

先按各工具或实验步骤清理 VPCS 和 OVS 连接，再在原工作目录执行::

  bash frr_init.sh -s

该命令删除清单中容器的同名 netns 登记，停止并删除容器。
它不是完整实验回收器，不代替 VPCS、OVS 或协议实验自身的清理步骤。
