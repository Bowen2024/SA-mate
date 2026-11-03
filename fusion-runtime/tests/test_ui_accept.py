"""5C controlled accept, immutable versions, receipts and conflict protection."""

from __future__ import annotations

import json
from pathlib import Path
import uuid

from ui_test_support import (
    DEFAULT_ROOT,
    DESIGN_PATH,
    MANIFEST_PATH,
    STATE_DIR,
    UiFixture,
    sha,
    tree_snapshot,
)

ENTRY = f"{DEFAULT_ROOT}/index.html"
APP = f"{DEFAULT_ROOT}/assets/app.js"
CSS = f"{DEFAULT_ROOT}/assets/styles.css"
OLD = f"{DEFAULT_ROOT}/assets/old.bin"
NEW = f"{DEFAULT_ROOT}/assets/new.bin"
README = f"{DEFAULT_ROOT}/README.md"


def request_id():
    return str(uuid.uuid4())


def candidate_files():
    return {
        ENTRY: "<!doctype html><title>V1</title>",
        APP: "const version='V1';\n",
        CSS: "body{color:black}\n",
        OLD: bytes(range(32)),
        README: "# 演示 V1\n\n未做浏览器验收。\n",
        DESIGN_PATH: "# UI 设计说明 Draft V1\n\n视觉待决。\n",
    }


def edit_candidate(workspace_path, files):
    workspace = Path(workspace_path)
    tree = workspace / "tree"
    for path in sorted(tree.rglob("*")):
        if path.is_file():
            relative = path.relative_to(tree).as_posix()
            if relative not in files:
                path.unlink()
    for relative, content in files.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    (workspace / "candidate.json").write_text(json.dumps({
        "schema_version": 1,
        "entrypoint": ENTRY,
        "files": sorted(files),
    }, ensure_ascii=False), encoding="utf-8")


class AcceptFixture(UiFixture):
    def prepare_ready(self, *, mode="empty", history_revision=None, files=None):
        read = self.read_context(identifier=20)
        prepared = self.prepare(read["read_id"], request_id(), mode,
                                history_revision=history_revision, identifier=21)
        edit_candidate(prepared["workspace_path"], candidate_files() if files is None else files)
        inspected = self.inspect_candidate(prepared["revision_id"], identifier=22)
        self.assertEqual(inspected["state"], "candidate_ready", inspected["issues"])
        return prepared, inspected

    def accept_ready(self, prepared, inspected, *, delete_paths=None):
        return self.accept(
            prepared["revision_id"], inspected["inspection_id"], request_id(),
            inspected["changes"]["removed"] if delete_paths is None else delete_paths,
            identifier=23,
        )

    def save_v1(self):
        self.write_inputs()
        self.connect(allow_write=True)
        protected = {
            path: sha((self.project_p1 / path).read_bytes())
            for path in ("README.md", "project.json", "docs/PRD.md", "docs/requirements.md")
        }
        prepared, inspected = self.prepare_ready()
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved", accepted)
        return accepted, protected


class FirstAcceptTests(AcceptFixture):
    def test_first_accept_materializes_complete_version_and_six_checks(self):
        protected_trees = {
            "foundation": tree_snapshot(self.foundation),
            "upstream": tree_snapshot(self.upstream),
            "other_project": tree_snapshot(self.project_p2),
        }
        accepted, protected = self.save_v1()
        revision = accepted["current_revision"]
        self.assertRegex(accepted["transaction_id"], r"^T-[0-9a-f]{32}$")
        self.assertFalse(accepted["receipt_replay"])
        self.assertEqual({item["code"] for item in accepted["verification"]},
                         {"document_set", "manifest", "pointer", "history",
                          "inputs", "unknown_files"})
        self.assertTrue(all(item["checked"] and item["passed"]
                            for item in accepted["verification"]))
        for relative, content in candidate_files().items():
            expected = content if isinstance(content, bytes) else content.encode("utf-8")
            self.assertEqual((self.project_p1 / relative).read_bytes(), expected)
            snapshot = (self.project_p1 / STATE_DIR / "versions" / revision
                        / "tree" / relative)
            self.assertEqual(snapshot.read_bytes(), expected)
        manifest = json.loads((self.project_p1 / MANIFEST_PATH).read_text())
        self.assertTrue(all(set(item) == {"path", "sha256"} for item in manifest["files"]))
        self.assertNotIn(MANIFEST_PATH, {item["path"] for item in manifest["files"]})
        pointer = json.loads((self.project_p1 / STATE_DIR / "current.json").read_text())
        self.assertEqual(pointer["revision_sha256"], revision)
        self.assertFalse((self.project_p1 / STATE_DIR / "transaction.json").exists())
        self.assertEqual(len(list((self.project_p1 / STATE_DIR / "versions").iterdir())), 1)
        receipt = json.loads((self.project_p1 / STATE_DIR / "requests"
                              / f"{accepted['request_id']}.json").read_text())
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["write_outcome"], "saved")
        for relative, expected in protected.items():
            self.assertEqual(sha((self.project_p1 / relative).read_bytes()), expected)
        self.assertEqual(tree_snapshot(self.foundation), protected_trees["foundation"])
        self.assertEqual(tree_snapshot(self.upstream), protected_trees["upstream"])
        self.assertEqual(tree_snapshot(self.project_p2), protected_trees["other_project"])
        reread = self.read_context(identifier=24)
        self.assertEqual(reread["state"], "stable")
        self.assertEqual(reread["current"]["revision_sha256"], revision)
        history = self.read_history(identifier=25, revision_sha256=revision)
        self.assertEqual(history["version"]["packet"]["files"], manifest["files"])

    def test_closed_candidate_cannot_be_inspected_for_another_accept(self):
        accepted, _protected = self.save_v1()
        result = self.inspect_candidate(accepted["revision_id"], identifier=26)
        self.assertEqual(result["state"], "candidate_closed")
        self.assertIsNone(result["inspection_id"])


class ChangeAndIdentityTests(AcceptFixture):
    def test_modify_add_delete_requires_exact_delete_set_and_preserves_history(self):
        first, _protected = self.save_v1()
        self.write(self.project_p1, f"{DEFAULT_ROOT}/user-note.txt", "keep me\n")
        files = candidate_files()
        del files[OLD]
        files[APP] = "const version='V2';\n"
        files[NEW] = b"\x00\xff\x10"
        prepared, inspected = self.prepare_ready(mode="current", files=files)
        self.assertEqual(inspected["changes"]["removed"], [OLD])
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1),
            "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"],
            "request_id": request_id(), "delete_paths": [],
        }, error=True)
        self.assertEqual(rejected["error"]["code"], "invalid_arguments")
        second = self.accept_ready(prepared, inspected)
        self.assertEqual(second["write_outcome"], "saved")
        self.assertFalse((self.project_p1 / OLD).exists())
        self.assertEqual((self.project_p1 / NEW).read_bytes(), b"\x00\xff\x10")
        self.assertEqual((self.project_p1 / f"{DEFAULT_ROOT}/user-note.txt").read_text(),
                         "keep me\n")
        old_snapshot = (self.project_p1 / STATE_DIR / "versions"
                        / first["current_revision"] / "tree" / OLD)
        self.assertEqual(old_snapshot.read_bytes(), bytes(range(32)))

    def test_unchanged_reuses_version_without_public_rewrite(self):
        first, _protected = self.save_v1()
        public_before = {
            relative: sha((self.project_p1 / relative).read_bytes())
            for relative in [*candidate_files(), MANIFEST_PATH, f"{STATE_DIR}/current.json"]
        }
        versions_before = tree_snapshot(self.project_p1 / STATE_DIR / "versions")
        prepared, inspected = self.prepare_ready(mode="current")
        unchanged = self.accept_ready(prepared, inspected)
        self.assertEqual(unchanged["write_outcome"], "unchanged")
        self.assertEqual(unchanged["current_revision"], first["current_revision"])
        self.assertIsNone(unchanged["transaction_id"])
        self.assertEqual(tree_snapshot(self.project_p1 / STATE_DIR / "versions"), versions_before)
        for relative, expected in public_before.items():
            self.assertEqual(sha((self.project_p1 / relative).read_bytes()), expected)

    def test_saved_receipt_replay_reports_actual_current_and_no_second_write(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        first_request = request_id()
        first_args = {
            "project_path": str(self.project_p1),
            "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"],
            "request_id": first_request, "delete_paths": [],
        }
        first = self.call(self.mcp.ACCEPT, first_args)
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        prepared_two, inspected_two = self.prepare_ready(mode="current", files=files)
        second = self.accept_ready(prepared_two, inspected_two)
        self.assertNotEqual(second["current_revision"], first["current_revision"])
        before = tree_snapshot(self.project_p1 / STATE_DIR / "versions")
        replay = self.call(self.mcp.ACCEPT, first_args, identifier=40)
        self.assertTrue(replay["receipt_replay"])
        self.assertEqual(replay["write_outcome"], "saved")
        self.assertEqual(replay["current_revision"], second["current_revision"])
        self.assertEqual(replay["versions"]["new"], first["current_revision"])
        self.assertEqual(tree_snapshot(self.project_p1 / STATE_DIR / "versions"), before)

    def test_changed_sources_get_a_new_content_identity(self):
        first, _protected = self.save_v1()
        self.write(self.project_p1, "docs/PRD.md",
                   "---\nartifact_kind: prd\nstatus: Draft\n---\n\n# PRD Draft V2\n")
        prepared, inspected = self.prepare_ready(mode="current")
        second = self.accept_ready(prepared, inspected)
        self.assertEqual(second["write_outcome"], "saved")
        self.assertNotEqual(second["current_revision"], first["current_revision"])


class ProtectionAndReceiptTests(AcceptFixture):
    def test_candidate_and_source_changes_after_inspection_are_rejected(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        before = tree_snapshot(self.project_p1 / "docs")
        self.write(Path(prepared["workspace_path"]), f"tree/{CSS}", "body{color:red}\n")
        changed = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(changed["error"]["code"], "candidate_changed")
        self.assertEqual(tree_snapshot(self.project_p1 / "docs"), before)

        prepared_two, inspected_two = self.prepare_ready()
        self.write(self.project_p1, "docs/PRD.md", "# changed after inspection\n")
        changed_source = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared_two["revision_id"],
            "inspection_id": inspected_two["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(changed_source["error"]["code"], "source_changed")

    def test_unmanaged_target_is_never_overwritten(self):
        first, _protected = self.save_v1()
        del first
        unknown = f"{DEFAULT_ROOT}/user-note.txt"
        self.write(self.project_p1, unknown, "third party\n")
        files = candidate_files()
        files[unknown] = "candidate overwrite\n"
        prepared, inspected = self.prepare_ready(mode="current", files=files)
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(rejected["error"]["code"], "unmanaged_target_exists")
        self.assertEqual((self.project_p1 / unknown).read_text(), "third party\n")

    def test_request_id_reuse_with_other_parameters_or_operation_is_rejected(self):
        accepted, _protected = self.save_v1()
        reused = self.call(self.mcp.PREPARE, {
            "project_path": str(self.project_p1), "read_id": "read-any",
            "request_id": accepted["request_id"], "mode": "current"}, error=True)
        self.assertEqual(reused["error"]["code"], "request_reused")
        changed = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": accepted["revision_id"],
            "inspection_id": "different", "request_id": accepted["request_id"],
            "delete_paths": [OLD]}, error=True)
        self.assertEqual(changed["error"]["code"], "request_reused")

    def test_legacy_collection_is_archived_before_first_managed_accept(self):
        self.write_inputs()
        files = candidate_files()
        for relative, content in files.items():
            self.write(self.project_p1, relative, content)
        manifest = {"schema_version": 1, "entrypoint": ENTRY, "files": [
            {"path": path, "sha256": sha(content if isinstance(content, bytes)
                                         else content.encode("utf-8"))}
            for path, content in sorted(files.items())]}
        self.write(self.project_p1, MANIFEST_PATH,
                   json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready(mode="current")
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved")
        old = accepted["versions"]["old"]
        self.assertIsNotNone(old)
        legacy = self.read_history(revision_sha256=old)
        self.assertEqual(legacy["version"]["origin"], "legacy")

    def test_history_restore_uses_current_sources_and_preserves_intermediate_versions(self):
        first, _protected = self.save_v1()
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        prepared_two, inspected_two = self.prepare_ready(mode="current", files=files)
        second = self.accept_ready(prepared_two, inspected_two)
        self.write(self.project_p1, "docs/PRD.md",
                   "---\nartifact_kind: prd\nstatus: Draft\n---\n\n# current inputs V3\n")
        restored_files = candidate_files()
        restored_files[DESIGN_PATH] = "# Draft restored against current inputs V3\n"
        prepared, inspected = self.prepare_ready(
            mode="history", history_revision=first["current_revision"], files=restored_files)
        base = json.loads((Path(prepared["workspace_path"]) / "base.json").read_text())
        self.assertEqual(base["restored_from"], first["current_revision"])
        self.assertNotEqual(base["sources"], json.loads(
            (self.project_p1 / STATE_DIR / "versions" / first["current_revision"]
             / "version.json").read_text())["packet"]["sources"])
        restored = self.accept_ready(prepared, inspected)
        self.assertEqual(restored["write_outcome"], "saved")
        self.assertNotEqual(restored["current_revision"], second["current_revision"])
        versions = {path.name for path in (self.project_p1 / STATE_DIR / "versions").iterdir()}
        self.assertTrue({first["current_revision"], second["current_revision"],
                         restored["current_revision"]} <= versions)

    def test_five_file_import_accept_preserves_source_and_maps_members(self):
        self.write_inputs()
        source_root = self.write_import_case()
        source_before = tree_snapshot(source_root)
        protected_root_readme = sha((self.project_p1 / "README.md").read_bytes())
        self.connect(allow_write=True, import_roots=[self.import_parent])
        read = self.read_context(import_source=self.import_source())
        prepared = self.prepare(read["read_id"], request_id(), "import")
        imported_files = {
            ENTRY: (source_root / "index.html").read_text(),
            APP: (source_root / "assets/app.js").read_text(),
            CSS: (source_root / "assets/styles.css").read_text(),
            README: (source_root / "README.md").read_text(),
            DESIGN_PATH: (source_root / "docs/ui-style.md").read_text(),
        }
        inspected = self.inspect_candidate(prepared["revision_id"])
        self.assertEqual(inspected["state"], "candidate_ready", inspected["issues"])
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved")
        for relative, expected in imported_files.items():
            self.assertEqual((self.project_p1 / relative).read_text(), expected)
        self.assertEqual(tree_snapshot(source_root), source_before)
        self.assertEqual(sha((self.project_p1 / "README.md").read_bytes()),
                         protected_root_readme)

    def test_registered_mutable_reference_blocks_accept_but_fixed_snapshot_does_not(self):
        self.save_v1()
        project_json = self.project_p1 / "project.json"
        data = json.loads(project_json.read_text())
        data["artifact_registry"] = {"schema_version": 1, "entries": {"A-1": {
            "artifact_id": "A-1", "versions": [{"content": {"type": "file", "path": APP}}],
        }}}
        project_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        files = candidate_files()
        files[APP] = "const version='registered-conflict';\n"
        prepared, inspected = self.prepare_ready(mode="current", files=files)
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(rejected["error"]["code"], "registered_path_in_use")

        data["artifact_registry"]["entries"]["A-1"]["versions"][0]["content"]["path"] = (
            f"{STATE_DIR}/versions/snapshot/{APP}")
        project_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        # The reference change is part of the protected closure, so prepare a
        # fresh candidate instead of reusing the old inspection credential.
        prepared_two, inspected_two = self.prepare_ready(mode="current", files=files)
        accepted = self.accept_ready(prepared_two, inspected_two)
        self.assertEqual(accepted["write_outcome"], "saved")

    def test_corrupt_registry_is_rejected_without_public_writes(self):
        self.save_v1()
        project_json = self.project_p1 / "project.json"
        data = json.loads(project_json.read_text())
        data["artifact_registry"] = {"schema_version": 1, "entries": []}
        project_json.write_text(json.dumps(data), encoding="utf-8")
        rejected = self.call(self.mcp.READ_CONTEXT,
                             {"project_path": str(self.project_p1)}, error=True)
        self.assertEqual(rejected["error"]["code"], "registry_unreadable")

    def test_lock_and_main_transaction_block_accept_without_consuming_inspection(self):
        self.save_v1()
        files = candidate_files()
        files[APP] = "const version='V2';\n"
        prepared, inspected = self.prepare_ready(mode="current", files=files)
        args = {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": [],
        }
        lock = self.project_p1 / ".project-state.lock"
        lock.write_text('{"operation":"other","pid":1}\n', encoding="utf-8")
        try:
            blocked = self.call(self.mcp.ACCEPT, args, error=True)
            self.assertEqual(blocked["error"]["code"], "lock_busy")
        finally:
            lock.unlink()
        journal = self.project_p1 / ".project-state-transaction.json"
        journal.write_text('{"schema_version":1}\n', encoding="utf-8")
        try:
            blocked = self.call(self.mcp.ACCEPT, args, error=True)
            self.assertEqual(blocked["error"]["code"], "main_transaction_pending")
        finally:
            journal.unlink()
        accepted = self.call(self.mcp.ACCEPT, args)
        self.assertEqual(accepted["write_outcome"], "saved")

    def test_indirect_manifest_reference_and_corrupt_nested_manifest_are_protected(self):
        self.save_v1()
        project_json = self.project_p1 / "project.json"
        data = json.loads(project_json.read_text())
        data["artifact_registry"] = {"schema_version": 1, "entries": {"A-set": {
            "artifact_id": "A-set", "versions": [{"content": {
                "type": "file-set", "manifest": {"path": MANIFEST_PATH},
            }}],
        }}}
        project_json.write_text(json.dumps(data), encoding="utf-8")
        prepared, inspected = self.prepare_ready(mode="current")
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(rejected["error"]["code"], "registered_path_in_use")

        nested = "docs/registered-manifest.json"
        self.write(self.project_p1, nested, "{not-json")
        data["artifact_registry"]["entries"]["A-set"]["versions"][0]["content"]["manifest"]["path"] = nested
        project_json.write_text(json.dumps(data), encoding="utf-8")
        unreadable = self.call(self.mcp.READ_CONTEXT,
                               {"project_path": str(self.project_p1)}, error=True)
        self.assertEqual(unreadable["error"]["code"], "registry_unreadable")

    def test_corrupt_accept_receipt_is_rejected_not_rewritten(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        args = {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": [],
        }
        accepted = self.call(self.mcp.ACCEPT, args)
        self.assertEqual(accepted["write_outcome"], "saved")
        receipt = self.project_p1 / STATE_DIR / "requests" / f"{args['request_id']}.json"
        receipt.write_text("{broken", encoding="utf-8")
        before = receipt.read_bytes()
        rejected = self.call(self.mcp.ACCEPT, args, error=True)
        self.assertEqual(rejected["error"]["code"], "receipt_invalid")
        self.assertEqual(receipt.read_bytes(), before)

    def test_second_candidate_cannot_overwrite_target_advanced_by_first_accept(self):
        first, _protected = self.save_v1()
        del first
        files_one = candidate_files()
        files_one[APP] = "const winner='one';\n"
        files_two = candidate_files()
        files_two[APP] = "const winner='two';\n"
        prepared_one, inspected_one = self.prepare_ready(mode="current", files=files_one)
        prepared_two, inspected_two = self.prepare_ready(mode="current", files=files_two)
        winner = self.accept_ready(prepared_one, inspected_one)
        self.assertEqual(winner["write_outcome"], "saved")
        loser = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1), "revision_id": prepared_two["revision_id"],
            "inspection_id": inspected_two["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(loser["error"]["code"], "target_changed")
        self.assertEqual((self.project_p1 / APP).read_text(), "const winner='one';\n")


class CredentialAndConsumptionTests(AcceptFixture):
    def test_inspection_id_cannot_cross_project(self):
        self.save_v1()
        prepared, inspected = self.prepare_ready(mode="current")
        other_before = tree_snapshot(self.project_p2)
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p2), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": []}, error=True)
        self.assertEqual(rejected["error"]["code"], "inspection_invalid")
        self.assertEqual(tree_snapshot(self.project_p2), other_before)

    def test_inspection_is_consumed_when_transaction_activates(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        args = {
            "project_path": str(self.project_p1), "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"], "request_id": request_id(),
            "delete_paths": [],
        }
        self.server.tools.failpoint = lambda event, _context: (
            (_ for _ in ()).throw(RuntimeError("injected")) if event == "before_first_write" else None)
        interrupted = self.call(self.mcp.ACCEPT, args, error=True)
        self.server.tools.failpoint = None
        transaction_id = interrupted["error"]["details"]["transaction_id"]
        self.recover(transaction_id, request_id(), "rollback")
        reused = self.call(self.mcp.ACCEPT, {**args, "request_id": request_id()}, error=True)
        self.assertEqual(reused["error"]["code"], "inspection_invalid")

    def test_credential_capacity_is_128_without_evicting_live_tokens(self):
        self.write_inputs()
        self.connect()
        before = tree_snapshot(self.project_p1)
        tokens = []
        for index in range(128):
            tokens.append(self.read_context(identifier=100 + index)["read_id"])
        self.assertEqual(len(set(tokens)), 128)
        overflow = self.call(self.mcp.READ_CONTEXT,
                             {"project_path": str(self.project_p1)}, error=True)
        self.assertEqual(overflow["error"]["code"], "limit_exceeded")
        self.assertEqual(tree_snapshot(self.project_p1), before)
