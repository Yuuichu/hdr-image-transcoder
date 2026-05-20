import pytest

from helpers import FIXTURES, LIBAVIF_DIR, LIBJXL_DIR, ROOT


@pytest.fixture(scope="session")
def repo_root():
    return ROOT


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES


@pytest.fixture(scope="session")
def hdr_jxl_fixture(fixtures_dir):
    return fixtures_dir / "test_hdr_fix.jxl"


@pytest.fixture(scope="session")
def avifgainmaputil():
    return LIBAVIF_DIR / "avifgainmaputil.exe"


@pytest.fixture(scope="session")
def avifgainmaputil_hdr():
    return LIBAVIF_DIR / "avifgainmaputil_hdr.exe"


@pytest.fixture(scope="session")
def avifdec():
    return LIBAVIF_DIR / "avifdec.exe"


@pytest.fixture(scope="session")
def cjxl():
    return LIBJXL_DIR / "cjxl.exe"
