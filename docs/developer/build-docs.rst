文档构建与版本发布
========================================

实现约定
----------------------------------------

本工程沿用参考 docs 的 Sphinx、Read the Docs 主题、中文、双 PDF 和不可覆盖版本归档方式。
配置与脚本已改为 route-ovs 命名；文档版本保存在本目录的 ``docs/.version``，
初始值为 ``v0.1``，表示文档框架版本，不代表 FRR 或 OVS 软件版本。

HTML 使用统一首页；用户和开发章节分别生成一本 PDF。
Sphinx 配置可参考 `官方配置文档 <https://www.sphinx-doc.org/en/master/usage/configuration.html>`_；
侧栏选项可参考 `主题文档 <https://sphinx-rtd-theme.readthedocs.io/en/stable/configuring.html>`_。

构建环境
----------------------------------------

需要 GNU Make 和 Python 3.10 或更高版本。建议从项目根目录进入文档目录创建独立环境::

  cd docs
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install -r requirements.txt

固定的依赖版本为 Sphinx 8.1.3、sphinx-rtd-theme 3.1.0。
如已具有兼容环境，也可直接使用系统中的 Sphinx。

PDF 另需 XeLaTeX、latexmk 和中文字体。Debian/Ubuntu 的安装示例::

  sudo apt-get install latexmk texlive-xetex texlive-lang-chinese \
    texlive-latex-extra texlive-fonts-recommended fonts-freefont-otf

构建命令
----------------------------------------

在 ``docs/`` 目录执行::

  make help
  make check
  make html
  make latex
  make pdf
  make all
  make versions
  make serve

``make check`` 检查文档与交叉引用；默认构建把 Sphinx 警告作为失败处理。
``make latex`` 只生成两本书的 LaTeX 源码，不需要安装 TeX，也不等于 PDF 编译成功。
``make pdf`` 在缺少 latexmk 或 XeLaTeX 时会明确报错。

产物位置：

* HTML：``html/index.html``。
* 用户 PDF：``pdf/user/route-ovs-user.pdf``。
* 开发 PDF：``pdf/developer/route-ovs-dev.pdf``。
* LaTeX 中间文件：``_build/latex/``。

``make serve`` 在本机 ``127.0.0.1:8000`` 提供静态预览，入口为 ``/html/index.html``。
``make clean`` 删除当前 HTML、PDF 和中间产物，保留 ``versions/``。
也可指定 ``SPHINXBUILD``、``PYTHON`` 和 ``SPHINXOPTS`` 使用其他构建环境。

按版本归档
----------------------------------------

将 ``docs/.version`` 改为本次文档发布标识，再执行::

  make archive
  make versions

归档需要 HTML 和两本 PDF 都构建成功。脚本核对版本与源码摘要，
拒绝归档缺失的产物、旧源码对应的产物或已有版本，不会覆盖历史记录。
生成的目录如下::

  versions/
  ├── index.html
  ├── catalog.js
  └── v0.1/
      ├── html/
      ├── pdf/user/route-ovs-user.pdf
      ├── pdf/developer/route-ovs-dev.pdf
      ├── source/
      ├── .version
      └── manifest.json

``source/`` 保存可重新构建的文档源码，包括本目录自己的 ``.version``。
``manifest.json`` 记录构建时间、源码摘要和归档文件 SHA-256。
同一功能版本下的文档修订应使用新标识，例如 ``v0.1-doc2``。

部署整个 ``docs/`` 对应的构建目录时，可同时访问当前版本与历史 HTML/PDF。
历史页面通过共享的 ``versions/catalog.js`` 更新版本列表，选择器兼容本地文件打开。
