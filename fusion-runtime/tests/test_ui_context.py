"""UI-T04—T09 and read-side UI-T16: project binding, paths, closure, limits."""

import json
import os
from pathlib import Path
import unicodedata

from ui_test_support import (
    DEFAULT_ROOT,
    DESIGN_PATH,
    MANIFEST_PATH,
    STATE_DIR,
    UiFixture,
    tree_snapshot,
)


def expect_error(case, name, arguments, code, identifier=3):
    response = case.rpc("tools/call", {"name": name, "arguments": arguments}, identifier)
    case.assertNotIn("error", response, response)
    result = response["result"]
    case.assertTrue(result["isError"], result)
    payload = json.loads(result["content"][0]["text"])
    case.assertEqual(payload["error"]["code"], code, payload)
    return payload


def read_args(project, **extra):
    return {"project_path": str(project), **extra}


class ProjectBindingTests(UiFixture):
    def test_chinese_project_binds_internal_id(self):
        self.connect()
        result = self.read_context()
        self.assertEqual(result["project"]["project_id"], "procurement-demo")
        self.assertEqual(result["project"]["project_path"], str(self.project_p1))
        self.assertTrue(result["read_id"].startswith("read-"))

    def test_two_projects_do_not_share_state(self):
        self.connect()
        first = self.read_context(project=self.project_p1)
        second = self.read_context(project=self.project_p2)
        self.assertNotEqual(first["project"]["project_id"], second["project"]["project_id"])
        again = self.read_context(project=self.project_p1)
        self.assertEqual(again["project"]["project_id"], "procurement-demo")

    def test_projects_root_uninitialized_and_identity_conflict(self):
        self.connect()
        plain = self.projects / "未初始化项目"
        plain.mkdir()
        expect_error(self, self.mcp.READ_CONTEXT, read_args(plain), "project_not_initialized", 10)
        expect_error(self, self.mcp.READ_CONTEXT, read_args(self.projects),
                     "path_not_allowed", 11)
        wrong = self.projects / "错误身份"
        wrong.mkdir()
        (wrong / "project.json").write_text(
            json.dumps({"schema_version": 1, "project_id": "someone-else"}), encoding="utf-8")
        (wrong / "README.md").write_text("x", encoding="utf-8")
        (wrong / ".gitignore").write_text("x", encoding="utf-8")
        expect_error(self, self.mcp.READ_CONTEXT, read_args(wrong),
                     "identity_conflict", 12)

    def test_symlink_project_rejected(self):
        self.connect()
        linked = self.projects / "链接项目"
        linked.symlink_to(self.project_p1, target_is_directory=True)
        expect_error(self, self.mcp.READ_CONTEXT, read_args(linked),
                     "path_not_allowed", 13)


class PathValidationTests(UiFixture):
    def test_injected_project_and_source_paths_rejected(self):
        self.connect()
        cases = [
            {"source_paths": ["../secret.md"]},
            {"source_paths": ["/etc/hosts"]},
            {"source_paths": ["docs//PRD.md"]},
            {"source_paths": ["docs\\PRD.md"]},
            {"source_paths": ["docs/.env"]},
            {"source_paths": [f"{STATE_DIR}/x"]},
            {"artifact_root": "../outside"},
            {"artifact_root": "docs"},
            {"artifact_root": "ui"},
            {"artifact_root": "materials"},
        ]
        for arguments in cases:
            with self.subTest(arguments):
                expect_error(self, self.mcp.READ_CONTEXT,
                             read_args(self.project_p1, **arguments),
                             "path_not_allowed", 20)

    def test_non_nfc_and_casefold_collision_rejected(self):
        self.connect()
        nfd = "mate\u0301rials/x.md"
        self.assertNotEqual(unicodedata.normalize("NFC", nfd), nfd)
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, source_paths=[f"{nfd}/x.md"]),
                     "path_not_allowed", 21)
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, source_paths=["docs/Docs/x.md"]),
                     "path_not_allowed", 22)

    def test_symlinked_source_rejected_as_unreadable(self):
        self.connect()
        outside = self.outside / "outside.md"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("x", encoding="utf-8")
        link_dir = self.project_p1 / "docs/链接"
        link_dir.mkdir(parents=True)
        (link_dir.parent / "linked.md").symlink_to(outside)
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, source_paths=["docs/linked.md"]),
                     "path_not_allowed", 23)

    def test_spaces_and_chinese_paths_accepted(self):
        self.connect()
        self.write(self.project_p1, "materials/设计 说明.md", "# 中文参考\n")
        result = self.read_context(source_paths=["materials/设计 说明.md"])
        self.assertEqual(result["state"], "empty")
        self.assertTrue(result["read_id"])


class ClosureTests(UiFixture):
    def test_fixed_closure_complete_and_baseline_digest_stable(self):
        self.connect()
        self.write_inputs()
        first = self.read_context()
        second = self.read_context(identifier=6)
        self.assertEqual(first["baseline_digest"], second["baseline_digest"])
        paths = {item["path"] for item in first["dependency_descriptors"]}
        for relative in ("project.json", "README.md", "docs/requirements.md", "docs/PRD.md",
                         "docs/tech-spec.md", "docs/decisions.md",
                         MANIFEST_PATH, f"{STATE_DIR}/current.json",
                         f"{STATE_DIR}/transaction.json", DEFAULT_ROOT):
            self.assertIn(relative, paths)
        missing = [item for item in first["dependency_descriptors"]
                   if item["kind"] == "file" and item["state"] == "missing"]
        self.assertTrue(missing)
        self.assertEqual({item["sha256"] for item in missing}, {"missing"})

    def test_read_is_strictly_read_only(self):
        self.connect()
        self.write_inputs()
        before = tree_snapshot(self.project_p1)
        foundation_before = tree_snapshot(self.foundation)
        self.read_context()
        self.read_context(identifier=7)
        self.assertEqual(before, tree_snapshot(self.project_p1))
        self.assertEqual(foundation_before, tree_snapshot(self.foundation))

    def test_mid_read_change_is_unstable_without_read_id(self):
        toggle = {"mutate": True}

        def between(_root):
            if toggle["mutate"]:
                self.write(self.project_p1, "docs/PRD.md", "中途变化\n")
                toggle["mutate"] = False

        self.connect(between_passes=between)
        self.write_inputs()
        result = self.read_context()
        self.assertEqual(result["state"], "unstable")
        self.assertIsNone(result["read_id"])
        self.assertTrue(any(item["code"] == "closure_changed" for item in result["diagnostics"]))

    def test_invalid_utf8_input_is_unreadable_not_missing(self):
        self.connect()
        path = self.project_p1 / "docs/PRD.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfe\x00")
        expect_error(self, self.mcp.READ_CONTEXT, read_args(self.project_p1),
                     "input_unreadable", 8)


class LimitsTests(UiFixture):
    def test_oversized_source_document(self):
        self.connect()
        self.write(self.project_p1, "materials/big.md", "x" * (128 * 1024 + 1))
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, source_paths=["materials/big.md"]),
                     "input_too_large", 30)

    def test_too_many_source_paths(self):
        self.connect()
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1,
                               source_paths=[f"materials/s{i}.md" for i in range(65)]),
                     "invalid_arguments", 31)

    def test_descriptor_limit(self):
        self.connect()
        # A legacy collection is tolerated, but a tree with more than 1024
        # protection descriptors must be refused rather than silently trimmed.
        files = self.v1_files()
        revision = self.build_static_version(self.project_p1, files,
                                              created_at="2026-11-02T05:00:00.000000Z")
        for relative, raw in files.items():
            self.write(self.project_p1, relative, raw)
        import ui_test_support
        files_list = [{"path": path, "sha256": ui_test_support.sha(
            raw if isinstance(raw, bytes) else raw.encode())}
                      for path, raw in sorted(files.items())]
        self.write(self.project_p1, MANIFEST_PATH,
                   json.dumps({"schema_version": 1,
                               "entrypoint": f"{DEFAULT_ROOT}/index.html",
                               "files": files_list}, ensure_ascii=False))
        stray_dir = f"{DEFAULT_ROOT}/stray"
        for index in range(1010):
            self.write(self.project_p1, f"{stray_dir}/n{index:04d}.html", "x")
        expect_error(self, self.mcp.READ_CONTEXT, read_args(self.project_p1),
                     "limit_exceeded", 32)

    def test_content_budget_omits_text_but_keeps_descriptors(self):
        self.connect()
        sources = [f"materials/b{i}.md" for i in range(8)]
        for index, relative in enumerate(sources):
            self.write(self.project_p1, relative, "y" * 110 * 1024)
        result = self.call(self.mcp.READ_CONTEXT, read_args(self.project_p1, source_paths=sources),
                           identifier=33)
        omitted = [item for item in result["contents"] if item["content_omitted"]]
        self.assertTrue(omitted)
        self.assertGreaterEqual(len(result["dependency_descriptors"]), 8)

    def test_binary_import_descriptor_does_not_utf8_decode(self):
        self.connect(import_roots=(self.import_parent,))
        self.write_import_case()
        blob = bytes(range(256)) * 4
        (self.import_parent / "assets/blob.bin").write_bytes(blob)
        spec = self.import_source(files=["index.html", "assets/app.js", "assets/styles.css",
                                          "README.md", "docs/ui-style.md", "assets/blob.bin"])
        result = self.call(self.mcp.READ_CONTEXT,
                           read_args(self.project_p1, import_source=spec), identifier=34)
        binary = [item for item in result["dependency_descriptors"]
                  if item["path"].endswith("blob.bin")][0]
        self.assertEqual(binary["size_bytes"], len(blob))
        content = [item for item in result["contents"] if item["key"].endswith("blob.bin")][0]
        self.assertIsNone(content["content"])


class DraftAndLayoutTests(UiFixture):
    def test_draft_and_missing_optional_documents_issue_read_id(self):
        self.connect()
        self.write_inputs()
        result = self.read_context()
        self.assertEqual(result["state"], "empty")
        self.assertTrue(result["read_id"])
        self.assertFalse(any(item["code"] == "confirmation_required"
                             for item in result["diagnostics"]))

    def test_legacy_manifest_readable_without_pointer(self):
        self.connect()
        files = self.v1_files()
        revision = self.build_static_version(self.project_p1, files,
                                              created_at="2026-11-02T05:00:00.000000Z")
        for relative, raw in files.items():
            self.write(self.project_p1, relative, raw)
        files_list = sorted(({"path": path,
                              "sha256": __import__("ui_test_support").sha(
                                  raw if isinstance(raw, bytes) else raw.encode())}
                             for path, raw in files.items()), key=lambda item: item["path"])
        self.write(self.project_p1, MANIFEST_PATH,
                   json.dumps({"schema_version": 1,
                               "entrypoint": f"{DEFAULT_ROOT}/index.html",
                               "files": files_list}, ensure_ascii=False))
        result = self.call(self.mcp.READ_CONTEXT, read_args(self.project_p1), identifier=40)
        self.assertEqual(result["current"]["kind"], "legacy")
        self.assertIsNone(result["current"]["revision_sha256"])
        self.assertEqual(result["state"], "stable")

    def test_unmanaged_existing_targets_rejected(self):
        self.connect()
        self.write(self.project_p1, DESIGN_PATH, "# 既有设计\n")
        expect_error(self, self.mcp.READ_CONTEXT, read_args(self.project_p1),
                     "unmanaged_target_exists", 41)
        spare = UiFixture()
        spare.setUp()
        self.addCleanup(spare.doCleanups)
        spare.connect()
        spare.write(spare.project_p1, f"{DEFAULT_ROOT}/stray.html", "x")
        expect_error(spare, spare.mcp.READ_CONTEXT, read_args(spare.project_p1),
                     "unmanaged_target_exists", 42)

    def test_unsupported_layout_rejected(self):
        self.connect()
        bad_manifest = {"schema_version": 1, "entrypoint": "docs/index.html",
                        "files": [{"path": "docs/index.html",
                                   "sha256": __import__("ui_test_support").sha(b"x")}]}
        self.write(self.project_p1, MANIFEST_PATH,
                   json.dumps(bad_manifest, ensure_ascii=False))
        self.write(self.project_p1, "docs/index.html", "x")
        expect_error(self, self.mcp.READ_CONTEXT, read_args(self.project_p1),
                     "unsupported_layout", 43)


class ImportReadValidationTests(UiFixture):
    def test_import_mapping_returned_and_root_authorization(self):
        self.write_import_case()
        self.connect(import_roots=(self.import_parent,))
        result = self.call(self.mcp.READ_CONTEXT,
                           read_args(self.project_p1, import_source=self.import_source()),
                           identifier=50)
        mapping = {item["source_path"]: item["target_path"]
                   for item in result["import_mapping"]}
        self.assertEqual(mapping["docs/ui-style.md"], DESIGN_PATH)
        self.assertEqual(mapping["README.md"], f"{DEFAULT_ROOT}/README.md")
        self.assertEqual(len(mapping), 5)

    def test_unauthorized_import_root_rejected(self):
        self.write_import_case()
        self.connect(import_roots=())
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, import_source=self.import_source()),
                     "path_not_allowed", 51)

    def test_import_secret_and_incomplete_spec_rejected(self):
        self.write_import_case()
        self.connect(import_roots=(self.import_parent,))
        (self.import_parent / ".env").write_text("SECRET=1", encoding="utf-8")
        spec = self.import_source(files=["index.html", "assets/app.js", "assets/styles.css",
                                          "README.md", "docs/ui-style.md", ".env"])
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, import_source=spec),
                     "path_not_allowed", 52)
        bad = self.import_source()
        bad["files"].remove("README.md")
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, import_source=bad),
                     "invalid_arguments", 53)

    def test_import_overlap_with_project_rejected(self):
        self.write_import_case()
        self.connect(import_roots=(self.import_parent,))
        self.assertFalse((self.project_p1 / "docs").exists())
        # An import root equal to the projects root overlaps and must be refused
        # even if passed at startup; a root under business projects is rejected.
        server = self.connect(import_roots=(self.projects,))
        spec = {"root": str(self.project_p1),
                "files": ["project.json"], "entrypoint": "project.json",
                "design_path": "project.json", "readme_path": "project.json"}
        expect_error(self, self.mcp.READ_CONTEXT,
                     read_args(self.project_p1, import_source=spec),
                     "path_not_allowed", 54)
