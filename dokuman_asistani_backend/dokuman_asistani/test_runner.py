from __future__ import annotations

import importlib.util
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner


class PytestTestRunner(DiscoverRunner):
    def _resolve_label(self, label: str) -> str:
        raw_path = Path(label)
        if raw_path.exists():
            return str(raw_path)

        spec = importlib.util.find_spec(label)
        if spec is not None:
            if spec.origin and spec.origin != "namespace":
                return spec.origin

            if spec.submodule_search_locations:
                return next(iter(spec.submodule_search_locations))

        project_path = Path(settings.BASE_DIR, *label.split("."))
        if project_path.with_suffix(".py").exists():
            return str(project_path.with_suffix(".py"))
        if project_path.exists():
            return str(project_path)

        return label

    def _build_pytest_args(self, test_labels: list[str]) -> list[str]:
        args: list[str] = []

        if self.failfast:
            args.append("-x")

        if self.verbosity >= 2:
            args.append("-vv")
        elif self.verbosity == 0:
            args.append("-q")

        args.extend(self._resolve_label(label) for label in test_labels if label)
        return args

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        try:
            import pytest
        except ImportError as exc:
            raise RuntimeError(
                "Pytest tabanli test akisi icin 'pytest' ve 'pytest-django' kurulu olmali."
            ) from exc

        return pytest.main(self._build_pytest_args(list(test_labels or [])))
