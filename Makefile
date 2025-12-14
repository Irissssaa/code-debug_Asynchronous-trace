TARGET ?= tests/tokio_test_project/target/debug/tokio_test_project

# 被调试项目根目录
PROJECT_DIR := $(abspath $(dir $(TARGET))/../..)

# 所有调试产物统一目录
RESULT_DIR := $(PROJECT_DIR)/async_trace_results

GDB ?= gdb
PYTHON ?= python3
PYTHONPATH := $(shell pwd)/venv/lib/python3.12/site-packages

.PHONY: all deps gdb run clean help

all: help

## Step 1: 生成 async_deps.json
deps:
	@echo "输出目录：$(RESULT_DIR)"
	@mkdir -p $(RESULT_DIR)
	@echo "生成 async_deps.json"
	$(PYTHON) src/core/dwarf/async_deps.py $(TARGET) --json > $(RESULT_DIR)/async_deps.json

## Step 2: 启动 GDB 并加载调试器命令
gdb:
	@echo "启动 GDB 并加载 Python 命令..."
	PYTHONPATH=$(PYTHONPATH) $(GDB) -q $(TARGET) -ex "source src/main.py"

## Step 3: 一键流程
run: deps gdb

## 清理调试产物
clean:
	@echo "清理调试输出 ($(RESULT_DIR))"
	rm -rf $(RESULT_DIR)

## 帮助
help:
	@echo "可用命令："
	@echo "  make deps   - 生成 async_deps.json"
	@echo "  make gdb    - 启动 GDB"
	@echo "  make run    - deps + gdb"
	@echo "  make clean  - 删除 async_trace_results"
	@echo ""
	@echo "调试输出目录：$(RESULT_DIR)"
