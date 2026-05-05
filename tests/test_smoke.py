"""Most basic smoke test — package imports."""


def test_import_src():
    import src

    assert src.__version__ == "0.1.0"


def test_import_subpackages():
    from src import envs, eval, llm, policies, training, utils  # noqa: F401
