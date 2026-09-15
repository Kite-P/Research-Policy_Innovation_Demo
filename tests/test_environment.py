import sys
from pathlib import Path

import duckdb
import numpy as np
import openpyxl
import pandas as pd
import pyarrow


def test_python_version():
    assert sys.version_info[:2] == (3, 13)


def test_running_inside_project_venv():
    prefix = Path(sys.prefix)

    assert prefix.name == ".venv"
    assert sys.prefix != sys.base_prefix


def test_core_packages_imported():
    assert pd.__version__
    assert np.__version__
    assert openpyxl.__version__
    assert pyarrow.__version__
    assert duckdb.__version__
