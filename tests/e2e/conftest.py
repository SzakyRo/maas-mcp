"""E2E tests conftest: empty by design.

Tests in this directory gate themselves via :func:`pytest.mark.skipif`
applied at module scope (see ``test_acquire_release.py``). The brief
originally proposed using ``collect_ignore_glob`` together with
``pytest_collection_modifyitems`` to re-enable collection, but those
two mechanisms don't compose: ``collect_ignore_glob`` prevents pytest
from collecting the test files at all, so the modifyitems hook never
sees them. The skipif-marker approach is correct.
"""
