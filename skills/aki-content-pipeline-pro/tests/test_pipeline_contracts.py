from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pipeline  # noqa: E402


def _skill_doc(operations: str) -> str:
    return textwrap.dedent(
        f"""\
        ---
        name: test-skill
        description: test
        ---

        ## Reusable Contract

        ```yaml
        version: 1
        operations:
        {operations}
        ```
        """
    )


class PipelineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sum_path = self.root / "summarizer.md"
        self.deai_path = self.root / "deai.md"
        self.original_paths = dict(pipeline.SKILL_PATHS)

    def tearDown(self) -> None:
        pipeline.SKILL_PATHS.clear()
        pipeline.SKILL_PATHS.update(self.original_paths)
        pipeline._load_skill_contract.cache_clear()
        self.tmp.cleanup()

    def _set_paths(self) -> None:
        pipeline.SKILL_PATHS.clear()
        pipeline.SKILL_PATHS.update(
            {
                "aki-text-note-summarizer": self.sum_path,
                "aki-deai-writing": self.deai_path,
            }
        )
        pipeline._load_skill_contract.cache_clear()

    def _write_happy_path_contracts(self) -> None:
        self.sum_path.write_text(
            _skill_doc(
                """\
                - draft
                - rewrite
                - heading_repair
                """
            )
            + textwrap.dedent(
                """\

                ### Operation: draft

                #### System Prompt
                ```text
                draft system
                ```

                #### User Template
                ```text
                {{extra_context}}
                {{source_text}}
                ```

                #### Output Contract
                ```yaml
                require_h1: true
                ban_numbered_subheadings: true
                generic_heading_prefixes:
                  - 总结
                ```

                ### Operation: rewrite

                #### Uses Operation
                ```yaml
                skill: aki-deai-writing
                operation: rewrite
                ```

                ### Operation: heading_repair

                #### System Prompt
                ```text
                heading system
                ```

                #### User Template
                ```text
                {{heading_issues}}
                {{draft_text}}
                ```

                #### Output Contract
                ```yaml
                require_h1: true
                ban_numbered_subheadings: true
                generic_heading_prefixes:
                  - 总结
                ```
                """
            ),
            encoding="utf-8",
        )
        self.deai_path.write_text(
            _skill_doc(
                """\
                - rewrite
                """
            )
            + textwrap.dedent(
                """\

                ### Operation: rewrite

                #### System Prompt
                ```text
                deai system
                ```

                #### User Template
                ```text
                {{extra_context}}
                {{draft_text}}
                ```

                #### Output Contract
                ```yaml
                require_h1: true
                ban_numbered_subheadings: true
                generic_heading_prefixes:
                  - 总结
                ```
                """
            ),
            encoding="utf-8",
        )
        self._set_paths()

    def test_load_and_resolve_nested_contracts(self) -> None:
        self._write_happy_path_contracts()

        summarizer = pipeline._load_skill_contract("aki-text-note-summarizer")
        deai = pipeline._load_skill_contract("aki-deai-writing")

        self.assertEqual(set(summarizer["operations"].keys()), {"draft", "rewrite", "heading_repair"})
        self.assertEqual(set(deai["operations"].keys()), {"rewrite"})

        visited: set[tuple[str, str]] = set()
        resolved = pipeline._resolve_contract_operation("aki-text-note-summarizer", "rewrite", visited)
        self.assertEqual(resolved["skill_name"], "aki-deai-writing")
        self.assertEqual(resolved["operation_name"], "rewrite")
        self.assertEqual(
            visited,
            {
                ("aki-text-note-summarizer", "rewrite"),
                ("aki-deai-writing", "rewrite"),
            },
        )

    def test_unknown_placeholder_fails(self) -> None:
        self.sum_path.write_text(
            _skill_doc(
                """\
                - draft
                """
            )
            + textwrap.dedent(
                """\

                ### Operation: draft

                #### System Prompt
                ```text
                draft system
                ```

                #### User Template
                ```text
                {{unknown_value}}
                ```

                #### Output Contract
                ```yaml
                require_h1: true
                ban_numbered_subheadings: true
                generic_heading_prefixes:
                  - 总结
                ```
                """
            ),
            encoding="utf-8",
        )
        self.deai_path.write_text(_skill_doc("- rewrite"), encoding="utf-8")
        self._set_paths()

        with self.assertRaises(RuntimeError):
            pipeline._load_skill_contract("aki-text-note-summarizer")

    def test_generate_core_note_draft_runs_in_fixed_order(self) -> None:
        self._write_happy_path_contracts()
        calls: list[tuple[str, str, float]] = []

        def fake_chat(system_prompt: str, user_prompt: str, model_override: str = "", temperature: float = 0.6) -> str:
            calls.append((system_prompt, user_prompt, temperature))
            if len(calls) == 1:
                return "# 母稿\n\n第一版"
            if len(calls) == 2:
                return "# 重写稿\n\n第二版"
            return "# 最终标题\n\n第三版"

        with mock.patch.object(pipeline, "chat_complete", side_effect=fake_chat):
            result = pipeline._generate_core_note_draft("原始资料", "额外上下文")

        self.assertEqual(result, "# 最终标题\n\n第三版")
        self.assertEqual([item[2] for item in calls], [0.6, 0.2, 0.3])
        self.assertIn("原始资料", calls[0][1])
        self.assertIn("额外上下文", calls[1][1])
        self.assertNotIn("1) 保留个人观点空间", calls[0][1])
        self.assertIn("no obvious structural issue", calls[2][1])

    def test_cycle_reference_fails(self) -> None:
        self.sum_path.write_text(
            _skill_doc(
                """\
                - rewrite
                """
            )
            + textwrap.dedent(
                """\

                ### Operation: rewrite

                #### Uses Operation
                ```yaml
                skill: aki-deai-writing
                operation: rewrite
                ```
                """
            ),
            encoding="utf-8",
        )
        self.deai_path.write_text(
            _skill_doc(
                """\
                - rewrite
                """
            )
            + textwrap.dedent(
                """\

                ### Operation: rewrite

                #### Uses Operation
                ```yaml
                skill: aki-text-note-summarizer
                operation: rewrite
                ```
                """
            ),
            encoding="utf-8",
        )
        self._set_paths()

        with self.assertRaises(RuntimeError):
            pipeline._resolve_contract_operation("aki-text-note-summarizer", "rewrite", set())

    def test_missing_contract_fails(self) -> None:
        self.sum_path.write_text("---\nname: x\n---\n", encoding="utf-8")
        self.deai_path.write_text("---\nname: y\n---\n", encoding="utf-8")
        self._set_paths()

        with self.assertRaises(RuntimeError):
            pipeline._load_skill_contract("aki-text-note-summarizer")


if __name__ == "__main__":
    unittest.main()
