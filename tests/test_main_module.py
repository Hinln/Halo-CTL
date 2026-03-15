import runpy

import pytest


def test_module_main_importable():
    with pytest.raises(SystemExit):
        runpy.run_module("halo_cli", run_name="__main__")
