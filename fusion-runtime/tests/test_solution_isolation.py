import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys

from solution_test_support import RUNTIME_ROOT, SOLUTION_SOURCE, REQUIREMENTS_SOURCE, SolutionFixture


MODERN_PROTOCOL = "2026-07-28"


class IsolationTests(SolutionFixture):
    """Step 7 invariant: the service runs from an isolated layout with a
    scrubbed interpreter environment and never reaches back into the source
    checkout, legacy buzz-develop-helper runtime code, or fusion-runtime-lab."""

    EXPECTED_SOLUTION_PY = {
        "mcp_server.py",
        "shared_loader.py",
        "configure_client.py",
        "file_tools/__init__.py",
        "file_tools/dependencies.py",
        "file_tools/solution.py",
    }

    def test_isolated_layout_excludes_legacy_runtime_and_links_resolve_in_temp(self):
        legacy_hits = [
            str(p) for p in self.install.rglob("*")
            if "buzz-develop-helper" in str(p) or "fusion-runtime-lab" in str(p)
        ]
        self.assertEqual(legacy_hits, [])

        installed_py = {
            str(p.relative_to(self.solution)) for p in self.solution.rglob("*.py")
        }
        self.assertEqual(installed_py, self.EXPECTED_SOLUTION_PY)

        upstream_files = {str(p.relative_to(self.upstream)) for p in self.upstream.rglob("*")
                          if p.is_file()}
        self.assertEqual(
            upstream_files,
            {
                "harness-core/specification/default/backend.md",
                "harness-core/skills/sdd-product-design/references/research-template.md",
            },
        )

        for link in (
            self.foundation / "methods/develop-helper",
            self.solution / "methods/develop-helper",
            self.solution / "templates/research-template.md",
        ):
            self.assertTrue(link.is_symlink(), link)
            target = link.resolve(strict=True)
            self.assertTrue(
                str(target).startswith(str(self.root)),
                f"{link} resolves outside the isolated root: {target}",
            )

    def _scrubbed_env(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}
        }
        env["PYTHONNOUSERSITE"] = "1"
        return env

    def _spawn_scrubbed(self, allow_save):
        command = [
            sys.executable, "-B", str(self.solution / "mcp_server.py"),
            "--foundation", str(self.foundation),
        ]
        if allow_save:
            command.append("--allow-save")
        return subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(self.root), env=self._scrubbed_env(),
        )

    def _shutdown(self, child, assert_zero=True):
        child.stdin.close()
        returncode = child.wait(timeout=5)
        stderr_text = child.stderr.read().decode("utf-8")
        child.stdout.close()
        child.stderr.close()
        if assert_zero:
            self.assertEqual(returncode, 0, stderr_text)

    def _rpc(self, child, message):
        child.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        child.stdin.flush()
        self.assertTrue(select.select([child.stdout], [], [], 5)[0], "stdio response timed out")
        return json.loads(child.stdout.readline())

    def _initialize(self, child, identifier):
        response = self._rpc(child, {
            "jsonrpc": "2.0", "id": identifier, "method": "initialize",
            "params": {"protocolVersion": MODERN_PROTOCOL, "capabilities": {}},
        })
        self.assertIn("result", response, response)
        self.assertEqual(
            response["result"]["serverInfo"]["name"], "solution-designer-file-tools"
        )
        child.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()

    def _call(self, child, identifier, name, arguments):
        response = self._rpc(child, {
            "jsonrpc": "2.0", "id": identifier, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return response["result"]["isError"], json.loads(response["result"]["content"][0]["text"])

    def _assert_no_source_tree_open(self, child):
        if shutil.which("lsof") is None:
            return
        listing = subprocess.run(
            ["lsof", "-p", str(child.pid)], capture_output=True, text=True
        )
        forbidden_roots = [
            str(SOLUTION_SOURCE),
            str(REQUIREMENTS_SOURCE),
            str(RUNTIME_ROOT.parent / "Develop_Helper"),
            str(RUNTIME_ROOT.parent / "buzz-develop-helper"),
            str(RUNTIME_ROOT.parent / "fusion-runtime-lab"),
        ]
        opened = [
            line.split()[-1].replace("\\ ", " ")
            for line in listing.stdout.splitlines()
            if " REG " in line
        ]
        leaked = [path for path in opened
                  if any(path.startswith(root) for root in forbidden_roots)]
        self.assertEqual(leaked, [])

    def test_scrubbed_process_runs_chain_and_rejects_cross_process_read_id(self):
        self.write_requirements_and_prd()
        self.confirm_prd()

        child = self._spawn_scrubbed(allow_save=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        self._initialize(child, 1)
        names = [tool["name"] for tool in self._rpc(child, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(
            names,
            ["solution_read_context", "solution_inspect",
             "solution_save_tech_spec_draft"],
        )

        is_error, read = self._call(child, 3, "solution_read_context",
                                    {"project_path": str(self.project_a)})
        self.assertFalse(is_error, read)
        self.assertEqual(read["confirmation"]["status"], "valid")
        self.assertTrue(read["read_receipt"]["save_eligible_at_read"])

        is_error, saved = self._call(child, 4, "solution_save_tech_spec_draft", {
            "project_path": str(self.project_a),
            "read_id": read["read_receipt"]["read_id"],
            "content": self.tech_spec(), "profile": "Lite"})
        self.assertFalse(is_error, saved)
        self.assertEqual(saved["write_outcome"], "saved", saved)
        self.assertTrue((self.project_a / "docs/tech-spec.md").is_file())

        self._assert_no_source_tree_open(child)

        _, next_read = self._call(child, 5, "solution_read_context",
                                  {"project_path": str(self.project_a)})
        unconsumed_id = next_read["read_receipt"]["read_id"]
        self._shutdown(child)

        other = self._spawn_scrubbed(allow_save=True)
        self.addCleanup(lambda: other.kill() if other.poll() is None else None)
        self._initialize(other, 10)
        is_error, rejected = self._call(other, 11, "solution_save_tech_spec_draft", {
            "project_path": str(self.project_a), "read_id": unconsumed_id,
            "content": self.tech_spec(), "profile": "Lite"})
        self.assertTrue(is_error)
        self.assertEqual(rejected["error"]["code"], "read_id_invalid")
        self._shutdown(other, assert_zero=False)

    def test_scrubbed_read_only_process_lists_two_tools_and_blocks_save(self):
        self.write_requirements_and_prd()
        self.confirm_prd()

        child = self._spawn_scrubbed(allow_save=False)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        self._initialize(child, 1)
        names = [tool["name"] for tool in self._rpc(child, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(names, ["solution_read_context", "solution_inspect"])

        is_error, blocked = self._call(child, 3, "solution_save_tech_spec_draft", {
            "project_path": str(self.project_a), "read_id": "unused",
            "content": self.tech_spec(), "profile": "Lite"})
        self.assertTrue(is_error)
        self.assertEqual(blocked["error"]["code"], "tool_not_enabled")
        self._shutdown(child)
