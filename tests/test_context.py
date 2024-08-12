import json

import pytest
from plumbum import local

import copier

from .helpers import build_file_tree, git_save


def test_exclude_templating_with_operation(tmp_path_factory: pytest.TempPathFactory) -> None:
    """
    Ensure it's possible to create one-off boilerplate files that are not
    managed during updates via _exclude using the ``_operation`` context variable.
    """
    src, dst, dst2 = map(tmp_path_factory.mktemp, ("src", "dst", "dst2"))

    template = r"{%- if _operation == 'update' %}boilerplate{%- endif %}"
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yml": f"_exclude:\n - \"{template}\"",
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",
                "boilerplate": "foo",
                "other_file": "foo",
            }
        )
        git_save(tag="1.0.0")
        build_file_tree(
            {
                "boilerplate": "bar",
                "other_file": "bar",
            }
        )
        git_save(tag="2.0.0")
    boilerplate = dst / "boilerplate"
    other_file = dst / "other_file"

    copier.run_copy(str(src), dst, defaults=True, overwrite=True, vcs_ref="1.0.0")
    for file in (boilerplate, other_file):
        assert file.exists()
        assert file.read_text() == "foo"

    with local.cwd(dst):
        git_save()

    copier.run_update(str(dst), overwrite=True)
    assert boilerplate.read_text() == "foo"  # This file is excluded from updates
    assert other_file.read_text() == "bar"

    # After using the worker for an `update` operation, reuse it for a `copy` again.
    # This checks that the cached `match_exclude` property is regenerated
    # after a context switch back from update to copy.
    copier.run_copy(str(src), dst2, defaults=True, overwrite=True, vcs_ref="1.0.0")
    for filename in ("boilerplate", "other_file"):
        assert (dst2 / filename).exists()
        assert (dst2 / filename).read_text() == "foo"


def test_task_templating_with_operation(
    tmp_path_factory: pytest.TempPathFactory
) -> None:
    """
    Ensure that it is possible to define tasks that are only executed when copying.
    """
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    task = {
        "command": ["{{ _copier_python }}", "-c", "from pathlib import Path; Path('foo').touch(exist_ok=False)"],
        "when": "{{ _operation == 'copy'}}",
    }
    with local.cwd(src):
        build_file_tree(
            {
                "copier.yml": f"_tasks: {json.dumps([task])}",
                "{{ _copier_conf.answers_file }}.jinja": "{{ _copier_answers|to_yaml }}",
            }
        )
        git_save(tag="1.0.0")

    copier.run_copy(str(src), dst, defaults=True, overwrite=True, unsafe=True)
    dst_file = dst / "foo"
    assert dst_file.exists()

    dst_file.unlink()
    with local.cwd(dst):
        git_save()

    copier.run_recopy(dst, defaults=True, overwrite=True, unsafe=True)
    assert dst_file.exists()

    dst_file.unlink()

    copier.run_update(dst, defaults=True, overwrite=True, unsafe=True)
    assert not dst_file.exists()
