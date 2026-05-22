import data_assistant


def test_package_exposes_version() -> None:
    assert data_assistant.__version__ == "0.1.0"
