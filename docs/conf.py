"""Sphinx configuration for the route-ovs user and developer guides."""
from pathlib import Path
import re


def _get_release():
    version_file = Path(__file__).resolve().parent / '.version'
    value = version_file.read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value):
        raise ValueError('Invalid or empty docs/.version')
    return value


project = 'route-ovs 文档'
author = 'route-ovs 项目组'
copyright = '2026, route-ovs 项目组'
release = _get_release()
version = release
language = 'zh_CN'
root_doc = 'index'

extensions = ['sphinx_rtd_theme']
html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'navigation_depth': 5,
    'collapse_navigation': False,
}
exclude_patterns = [
    'html', 'pdf', '_build', 'versions', '_scripts', '.venv',
    '**/__pycache__', 'Thumbs.db', '.DS_Store',
]
html_static_path = ['_static']
html_js_files = ['version-config.js', 'version-switch.js']
html_css_files = ['version-switch.css']

latex_engine = 'xelatex'
latex_documents = [
    ('user/index', 'route-ovs-user.tex', 'route-ovs 用户指南', author, 'manual'),
    ('developer/index', 'route-ovs-dev.tex', 'route-ovs 开发指南', author, 'manual'),
]
