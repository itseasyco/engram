#!/usr/bin/env python3
"""Tests for backend abstraction: ABC, factory, subclass checks, interface consistency."""

import os
import sqlite3
import sys
import tempfile
from abc import ABC
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backends"))

from backends import ContextBackend, get_backend
from backends.lcm_backend import LCMBackend
from backends.file_backend import FileBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_valid_lcm_db(path):
    """Create a valid LCM database with the summaries table."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE summaries (
            summary_id TEXT PRIMARY KEY,
            content TEXT,
            source TEXT DEFAULT 'lcm',
            citations TEXT DEFAULT '[]',
            project TEXT DEFAULT '',
            agent TEXT DEFAULT '',
            timestamp TEXT DEFAULT '',
            conversation_id TEXT DEFAULT '',
            parent_id TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}'
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# ABC Tests
# ---------------------------------------------------------------------------

class TestContextBackendIsAbstract:
    """Test that ContextBackend is a proper abstract class."""

    def test_context_backend_is_abc(self):
        assert issubclass(ContextBackend, ABC)

    def test_cannot_instantiate_context_backend(self):
        with pytest.raises(TypeError):
            ContextBackend()

    def test_cannot_instantiate_with_only_one_method(self):
        class Partial(ContextBackend):
            def fetch_summary(self, summary_id):
                return {}

        with pytest.raises(TypeError):
            Partial()

    def test_cannot_instantiate_missing_is_available(self):
        class AlmostComplete(ContextBackend):
            def fetch_summary(self, summary_id): return {}
            def discover_summaries(self, filters): return []
            def find_context(self, task, project=None, limit=10): return []
            def traverse_dag(self, summary_id, depth=3): return {}
            def backend_name(self): return "test"
            # is_available is missing

        with pytest.raises(TypeError):
            AlmostComplete()

    def test_cannot_instantiate_missing_backend_name(self):
        class MissingName(ContextBackend):
            def fetch_summary(self, summary_id): return {}
            def discover_summaries(self, filters): return []
            def find_context(self, task, project=None, limit=10): return []
            def traverse_dag(self, summary_id, depth=3): return {}
            def is_available(self): return True
            # backend_name is missing

        with pytest.raises(TypeError):
            MissingName()

    def test_complete_subclass_instantiates(self):
        class Complete(ContextBackend):
            def fetch_summary(self, summary_id): return {}
            def discover_summaries(self, filters): return []
            def find_context(self, task, project=None, limit=10): return []
            def traverse_dag(self, summary_id, depth=3): return {}
            def backend_name(self): return "test"
            def is_available(self): return True

        inst = Complete()
        assert inst.backend_name() == "test"


# ---------------------------------------------------------------------------
# get_backend Factory Tests
# ---------------------------------------------------------------------------

class TestGetBackendFactory:
    """Tests for the get_backend() config-driven factory."""

    @patch("backends.lcm_backend.LCMBackend.is_available", return_value=True)
    def test_returns_lcm_backend_for_lossless_claw(self, _mock_avail):
        backend = get_backend({"contextEngine": "lossless-claw"})
        assert isinstance(backend, LCMBackend)

    def test_returns_file_backend_for_none_engine(self):
        backend = get_backend({"contextEngine": None})
        assert isinstance(backend, FileBackend)

    def test_returns_file_backend_for_missing_engine(self):
        backend = get_backend({})
        assert isinstance(backend, FileBackend)

    @patch("backends.lcm_backend.LCMBackend.is_available", return_value=False)
    def test_raises_value_error_when_lcm_unavailable(self, _mock_avail):
        with pytest.raises(ValueError, match="lossless-claw backend requested"):
            get_backend({"contextEngine": "lossless-claw"})

    def test_raises_with_real_missing_db(self):
        config = {
            "contextEngine": "lossless-claw",
            "lcmDbPath": "/nonexistent/path/lcm.db",
        }
        with pytest.raises(ValueError, match="lossless-claw backend requested"):
            get_backend(config)

    def test_raises_when_db_has_no_summaries_table(self, tmp_path):
        db = tmp_path / "no_summaries.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE other_table (id TEXT)")
        conn.commit()
        conn.close()

        config = {"contextEngine": "lossless-claw", "lcmDbPath": str(db)}
        with pytest.raises(ValueError, match="lossless-claw backend requested"):
            get_backend(config)

    def test_returns_lcm_backend_with_real_db(self, tmp_path):
        db = tmp_path / "lcm.db"
        _create_valid_lcm_db(db)
        config = {"contextEngine": "lossless-claw", "lcmDbPath": str(db)}
        backend = get_backend(config)
        assert isinstance(backend, LCMBackend)

    def test_file_backend_never_raises(self):
        backend = get_backend({"contextEngine": None, "vaultPath": "/nonexistent"})
        assert isinstance(backend, FileBackend)


# ---------------------------------------------------------------------------
# Required Methods
# ---------------------------------------------------------------------------

class TestAbstractMethods:
    """Both backends must implement every abstract method."""

    REQUIRED_METHODS = (
        "fetch_summary",
        "discover_summaries",
        "find_context",
        "traverse_dag",
        "backend_name",
        "is_available",
    )

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_lcm_backend_has_method(self, method_name):
        assert callable(getattr(LCMBackend, method_name, None))

    @pytest.mark.parametrize("method_name", REQUIRED_METHODS)
    def test_file_backend_has_method(self, method_name):
        assert callable(getattr(FileBackend, method_name, None))


# ---------------------------------------------------------------------------
# Backend Names
# ---------------------------------------------------------------------------

class TestBackendNames:
    """backend_name() must return the expected identifier string."""

    def test_lcm_backend_name(self):
        backend = LCMBackend({})
        assert backend.backend_name() == "lossless-claw"

    def test_file_backend_name(self):
        backend = FileBackend({})
        assert backend.backend_name() == "file"


# ---------------------------------------------------------------------------
# is_available Contract
# ---------------------------------------------------------------------------

class TestIsAvailable:
    """Basic is_available() contract checks."""

    def test_file_backend_always_available(self):
        backend = FileBackend({})
        assert backend.is_available() is True

    def test_lcm_backend_unavailable_without_db(self):
        backend = LCMBackend({"lcmDbPath": "/nonexistent/lcm.db"})
        assert backend.is_available() is False

    def test_lcm_backend_available_with_valid_db(self, tmp_path):
        db = tmp_path / "lcm.db"
        _create_valid_lcm_db(db)
        backend = LCMBackend({"lcmDbPath": str(db)})
        assert backend.is_available() is True


# ---------------------------------------------------------------------------
# Liskov Substitution / Interface Consistency
# ---------------------------------------------------------------------------

class TestLiskovSubstitution:
    """Both backends can be used interchangeably through the ContextBackend interface."""

    @pytest.fixture()
    def lcm_backend(self, tmp_path):
        db = tmp_path / "lcm.db"
        _create_valid_lcm_db(db)
        return LCMBackend({"lcmDbPath": str(db)})

    @pytest.fixture()
    def file_backend(self):
        return FileBackend({
            "files": [],
            "memoryRoot": "/nonexistent",
            "vaultPath": "/nonexistent",
        })

    def test_fetch_summary_returns_dict(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            result = backend.fetch_summary("no-such-id")
            assert isinstance(result, dict)

    def test_discover_summaries_returns_list(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            result = backend.discover_summaries({})
            assert isinstance(result, list)

    def test_find_context_returns_list(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            result = backend.find_context("deploy treasury")
            assert isinstance(result, list)

    def test_traverse_dag_returns_dict_with_keys(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            result = backend.traverse_dag("no-such-id")
            assert isinstance(result, dict)
            assert "root" in result
            assert "chain" in result
            assert "depth_reached" in result

    def test_backend_name_returns_str(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            assert isinstance(backend.backend_name(), str)

    def test_is_available_returns_bool(self, lcm_backend, file_backend):
        for backend in [lcm_backend, file_backend]:
            assert isinstance(backend.is_available(), bool)

    def test_polymorphic_usage_through_base_type(self, file_backend):
        backend: ContextBackend = file_backend
        assert backend.backend_name() in ("lossless-claw", "file")
        assert isinstance(backend.is_available(), bool)
        assert isinstance(backend.fetch_summary("x"), dict)
        assert isinstance(backend.discover_summaries({}), list)
        assert isinstance(backend.find_context("task"), list)
        assert isinstance(backend.traverse_dag("x"), dict)
