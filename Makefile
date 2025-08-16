.PHONY: test-gdb venv clean-venv

venv: 
	python3 -m venv venv
	. venv/bin/activate && pip3 install -r src/requirements.txt

# Clean and recreate virtual environment (useful if typing conflicts occur)
clean-venv:
	rm -rf venv
	$(MAKE) venv

build-tokio-test:
	cargo build --manifest-path tests/tokio_test_project/Cargo.toml

build-future-executor-test:
	cargo build --manifest-path tests/future_executor_test/Cargo.toml

test-gdb: 
	@if [ -d "venv/lib/python3.12/site-packages" ]; then \
		PYTHONPATH="venv/lib/python3.12/site-packages:$$PYTHONPATH" gdb -x src/main.py --args tests/embassy_test/target/thumbv7m-none-eabi/debug/blinky; \
	else \
		VENV_SITE_PACKAGES=$$(find venv/lib -name "site-packages" -type d | head -1); \
		PYTHONPATH="$$VENV_SITE_PACKAGES:$$PYTHONPATH" gdb -x src/main.py --args tests/embassy_test/target/thumbv7m-none-eabi/debug/blinky; \
	fi

test-dwarf-analyzer: 
	venv/bin/python src/core/dwarf/async_deps.py tests/embassy_test/target/thumbv7m-none-eabi/debug/blinky --json > results/async_dependencies.json

# 新增目标，专门用于调试 QEMU 中运行的远程 Embassy 程序
test-gdb-embassy:
	@if [ -d "venv/lib/python3.12/site-packages" ]; then \
		PYTHONPATH="venv/lib/python3.12/site-packages:$$PYTHONPATH" gdb -ex "target remote localhost:1234" -x src/main.py --args tests/embassy_test/target/thumbv7m-none-eabi/debug/blinky; \
	else \
		VENV_SITE_PACKAGES=$$(find venv/lib -name "site-packages" -type d | head -1); \
		PYTHONPATH="$$VENV_SITE_PACKAGES:$$PYTHONPATH" gdb -ex "target remote localhost:1234" -x src/main.py --args tests/embassy_test/target/thumbv7m-none-eabi/debug/blinky; \
	fi
