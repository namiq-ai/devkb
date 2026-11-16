PY ?= .venv/bin/python
OUT := .verify

.PHONY: dev test verify paper

dev:
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -e ".[dev]"

test:
	$(PY) -m pytest tests -q

verify:
	mkdir -p $(OUT)
	cd study/analysis && ../../$(PY) analyze.py ../runs/sonnet/A.jsonl ../runs/sonnet/B.jsonl ../runs/sonnet/C.jsonl ../runs/sonnet/D.jsonl --model sonnet --out ../../$(OUT)/results-sonnet.json > /dev/null
	cd study/analysis && ../../$(PY) analyze.py ../runs/haiku/A.jsonl ../runs/haiku/B.jsonl ../runs/haiku/C.jsonl ../runs/haiku/D.jsonl --model haiku --out ../../$(OUT)/results-haiku.json > /dev/null
	cd study/analysis && ../../$(PY) analyze_ablation.py ../runs/ablation --out ../../$(OUT)/ablation.json > /dev/null
	cd study/analysis && ../../$(PY) analyze_process.py ../runs/process/A.jsonl ../runs/process/B.jsonl --out ../../$(OUT)/results-process.json > /dev/null
	@for f in results-sonnet results-haiku ablation results-process; do \
	  cmp -s $(OUT)/$$f.json study/results/$$f.json && echo "$$f: identical" || { echo "$$f: DIFFERS"; exit 1; }; done
	cd study/preregistration && sha256sum -c PREREGISTRATION.sha256 PREREGISTRATION-ADDENDUM-1.sha256 2>/dev/null | grep -v "^20"

paper:
	cd study/paper && pdflatex -interaction=nonstopmode paper.tex > /dev/null && bibtex paper > /dev/null && \
	  pdflatex -interaction=nonstopmode paper.tex > /dev/null && pdflatex -interaction=nonstopmode paper.tex | grep "Output written"

# C/C++ corpus check (ADR-DEVKB-008 §7, DKB-006): clones five pinned repositories to $(DEVKB_CPP_CORPUS)
# (default ~/.cache/devkb/cpp-corpus), measures caller precision/recall against an independent truth, the Complete
# rule, build time and the dependency list. Needs network on first run; deliberately not part of gate-1 or gate-2.
.PHONY: cpp-check
cpp-check:
	$(PY) -m devkb.bench.cpp_corpus $(ARGS)
