测试与验证
========================================

脚本基础检查
----------------------------------------

在项目根目录执行::

  bash -n script/frr_init.sh
  python3 -m py_compile script/frr_topology.py script/frr_vpcs.py

现有单元测试
----------------------------------------

工作区提供 ``tests/test_frr_topology.py`` 和 ``tests/test_frr_vpcs.py``。
可运行::

  python3 -m unittest discover -s tests -p 'test_*.py' -v

这些测试包含 mock 或命令桩；通过单元测试不代表已经完成真实 Docker、OVS 和协议验证。
脚本与测试应来自匹配的源码版本；存在未集成的命令时，先核对实现和测试的对应关系。

网络命名空间集成检查
----------------------------------------

``tests/check_vpcs_netns.py`` 使用真实 veth 和报文，但用 netns 进程替代 Docker 生命周期。
在支持非特权用户命名空间的 Linux 环境中可按脚本说明执行::

  unshare --user --map-root-user --net python3 tests/check_vpcs_netns.py

完整实验验证
----------------------------------------

后续协议用例需要记录容器创建、OVS 接入、VPCS 连通性、邻居建立、路由收敛、
抓包和资源清理。测试结果应标明源码版本、镜像版本和实际运行环境。
CI 接入方式及协议测试矩阵：待补充。
