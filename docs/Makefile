SPHINXBUILD   ?= sphinx-build
PYTHON        ?= python3
SPHINXOPTS    ?= -W --keep-going
VERSION_TOOL  = _scripts/version_docs.py
SOURCEDIR     = .
BUILDDIR      = html
PDFBUILDDIR   = _build/latex
PDFDIR        = pdf

.DEFAULT_GOAL := help
.PHONY: help check html latex pdf all clean archive versions serve

help:
	@echo "Documentation targets (run inside docs/):"
	@echo "  make check     Validate sources and cross-references"
	@echo "  make html      Build both guides as HTML in html/"
	@echo "  make latex     Generate sources for the two PDF guides"
	@echo "  make pdf       Build PDFs in pdf/user/ and pdf/developer/"
	@echo "  make all       Build HTML and PDF"
	@echo "  make archive   Build and archive docs/.version (no overwrite)"
	@echo "  make versions  List archived documentation versions"
	@echo "  make serve     Serve docs/ at http://127.0.0.1:8000/html/"
	@echo "  make clean     Remove current outputs; preserve versions/"
	@echo "PDF requires latexmk, XeLaTeX and Chinese fonts; see developer/build-docs.rst."

check:
	$(SPHINXBUILD) $(SPHINXOPTS) -n -b dummy "$(SOURCEDIR)" "_build/check"

html:
	$(SPHINXBUILD) $(SPHINXOPTS) -b html "$(SOURCEDIR)" "$(BUILDDIR)"
	$(PYTHON) $(VERSION_TOOL) record-html

latex:
	$(SPHINXBUILD) $(SPHINXOPTS) -b latex "$(SOURCEDIR)" "$(PDFBUILDDIR)"

pdf:
	@command -v latexmk >/dev/null 2>&1 || { echo "Missing latexmk; see developer/build-docs.rst." >&2; exit 1; }
	@command -v xelatex >/dev/null 2>&1 || { echo "Missing XeLaTeX; see developer/build-docs.rst." >&2; exit 1; }
	$(MAKE) latex
	$(MAKE) -C "$(PDFBUILDDIR)" all-pdf
	mkdir -p "$(PDFDIR)/user" "$(PDFDIR)/developer"
	cp "$(PDFBUILDDIR)/route-ovs-user.pdf" "$(PDFDIR)/user/route-ovs-user.pdf"
	cp "$(PDFBUILDDIR)/route-ovs-dev.pdf" "$(PDFDIR)/developer/route-ovs-dev.pdf"
	$(PYTHON) $(VERSION_TOOL) record-pdf

all: html pdf

archive:
	$(PYTHON) $(VERSION_TOOL) check
	$(MAKE) all
	$(PYTHON) $(VERSION_TOOL) archive

versions:
	$(PYTHON) $(VERSION_TOOL) list

serve:
	$(PYTHON) -m http.server 8000 --bind 127.0.0.1

clean:
	rm -rf "$(BUILDDIR)" "_build" "$(PDFDIR)"
