route-ovs 文档
========================================

route-ovs 使用 Docker、Open vSwitch（OVS）和 Linux 网络命名空间搭建
FRRouting（FRR）路由实验环境，并提供容器管理、抓包、拓扑展示和 VPCS 直连工具。

用户指南介绍环境准备、实验操作和排障；开发指南介绍工程结构、镜像构建、
脚本维护、测试与文档发布。当前为初始文档框架，已核对的操作按现有源码编写，
尚未完成的协议实验以“待补充”标注。

.. toctree::
   :maxdepth: 1
   :caption: 用户指南

   user/index

.. toctree::
   :maxdepth: 1
   :caption: 开发指南

   developer/index
