镜像构建
========================================

VPCS 镜像
----------------------------------------

项目提供 ``docker/devices/vpcs/Dockerfile``。从项目根目录构建::

  docker build -f docker/devices/vpcs/Dockerfile -t alpine/vpcs:latest .

当前基础镜像为 ``alpine:3.23``，安装 iproute2、iputils、traceroute、tcpdump、
dhcpcd、bind-tools 和 nmap-nping，默认命令为 ``sleep infinity``。
调整标签后，调用 VPCS 脚本时需同步指定 ``--image``。

FRR 镜像
----------------------------------------

本工程提供 ``devices/route/frr.tar.xz``，当前没有随本工程保存 FRR 构建 Dockerfile。
``frr_init.sh`` 的默认镜像是 ``quay.io/frrouting/frr:10.0.0``，应核对实际标签和版本。

待补充：FRR 源码地址与提交、构建命令、启用的协议组件、运行依赖和镜像验证步骤。
从外部 FRR 源码工程构建时，所需运行工具应安装在最终镜像阶段。

镜像交付
----------------------------------------

发布时记录镜像标签、镜像 ID、构建源码版本和归档校验值。
构建、加载和部署是独立步骤；重新构建镜像后，已有容器仍需按实验流程重建。
自动打包脚本、版本规则及离线交付清单：待补充。
