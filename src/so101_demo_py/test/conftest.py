from pathlib import Path


def pytest_addoption(parser) -> None:
    parser.addoption("--installed-share", type=Path, default=None)
