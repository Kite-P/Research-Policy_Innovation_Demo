import importlib.metadata


def test_akshare_version_is_frozen():
    assert importlib.metadata.version("akshare") == "1.18.96"
