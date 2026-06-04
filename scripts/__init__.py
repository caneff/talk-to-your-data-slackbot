"""Operator glue scripts for the Data Assistant.

Thin CLIs over the tested ``data_assistant`` package, invoked by maintainers and
triage skills. Kept out of the shipped wheel (see ``[tool.hatch.build]`` in
``pyproject.toml``); type-checked and tested via the ``scripts`` entries in
``[tool.pyright]`` and ``[tool.pytest.ini_options]``.
"""
