镜像构建
========================================

VPCS 镜像
----------------------------------------

项目提供 ``docker/devices/vpcs/Dockerfile``。从项目根目录构建::

  docker build -f docker/devices/vpcs/Dockerfile -t alpine/vpcs:latest .

当前基础镜像为 ``alpine:3.23``，安装 iproute2、iputils、traceroute、tcpdump、
dhcpcd、bind-tools 和 nmap-nping，默认命令为 ``sleep infinity``。
调整标签后，调用 VPCS 脚本时需同步指定 ``--image``。

FRR 镜像与 frr.tar 编译
----------------------------------------

构建流程为：获取 FRR 的 GitHub 源码，将本工程的 Dockerfile 复制到 FRR
源码树，再在 FRR 源码根目录运行构建脚本。最后通过 ``docker save`` 导出镜像归档。
以下命令在 Linux 宿主机执行，需要 Git、可访问的 Docker，以及构建依赖的网络下载条件。

1. 获取 FRR 源码
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

首次获取源码时执行::

  mkdir -p /home/alexan/program/github
  cd /home/alexan/program/github
  git clone https://github.com/FRRouting/frr.git
  cd frr

如果 ``/home/alexan/program/github/frr`` 已有源码，直接进入该目录，不必重复克隆。
发布构建应先选择已验证的分支、标签或提交，并记录源码版本::

  git rev-parse HEAD

2. 替换 Alpine Dockerfile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 FRR 源码根目录执行::

  cd /home/alexan/program/github/frr
  cp /home/alexan/program/test/route-ovs/docker/devices/route/Dockerfile.frr \
    docker/alpine/Dockerfile

本工程中的实际目录名是 ``docker/devices/route/``，其中 ``devices`` 为复数。
该步骤覆盖 FRR 源码中的 ``docker/alpine/Dockerfile``；如该文件已有需保留的修改，
先保存修改再复制。需要在运行容器中使用的软件包应安装在 Dockerfile 的最终运行阶段。

3. 执行 FRR 构建脚本
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

仍在 FRR 源码根目录执行::

  ./docker/alpine/build.sh

脚本的构建上下文是当前目录，不能进入 ``docker/alpine/`` 后再执行。
按当前构建脚本，成功后生成镜像 ``alpine/frr:latest``，并将构建生成的 APK
复制到 FRR 源码目录的 ``docker/alpine/pkgs/``。
构建完成后可以检查镜像和 FRR 命令版本::

  docker image inspect alpine/frr:latest
  docker run --rm --entrypoint vtysh alpine/frr:latest --version

该检查确认镜像与程序可用，协议功能还需通过对应实验验证。

4. 导出 frr.tar
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``build.sh`` 生成 Docker 镜像，不自动生成 ``frr.tar``。需要交付镜像文件时执行::

  docker save -o /home/alexan/program/test/route-ovs/devices/route/frr.tar \
    alpine/frr:latest

需要生成项目约定的 ``frr.tar.xz`` 时，再使用宿主机的 ``xz`` 压缩::

  xz -T0 -k /home/alexan/program/test/route-ovs/devices/route/frr.tar

``-k`` 保留原始 ``frr.tar``。同名 ``frr.tar.xz`` 已存在时，xz 会拒绝覆盖，
应先核对并处理旧交付文件，再执行压缩。

在实验主机加载未压缩或压缩的归档，例如::

  docker load -i /home/alexan/program/test/route-ovs/devices/route/frr.tar

加载后核对 ``script/frr_init.sh`` 中的 ``CONTAINER_IMG`` 是否指向
``alpine/frr:latest``。若使用其他标签，需同步调整镜像标签和启动配置。

镜像交付
----------------------------------------

发布时记录镜像标签、镜像 ID、构建源码版本和归档校验值。
构建、加载和部署是独立步骤；重新构建镜像后，已有容器仍需按实验流程重建。
自动打包脚本、版本规则及离线交付清单：待补充。
