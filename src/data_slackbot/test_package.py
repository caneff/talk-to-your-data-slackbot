import data_slackbot


def test_package_exposes_version() -> None:
    assert data_slackbot.__version__ == "0.1.0"
