"""Check the configuration contract used by newly created default projects."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pycore.core.config import BaseSettings, ConfigManager
from pycore.core.exceptions import ConfigurationError
from scripts.sdd_project import copy_harness


class Settings(BaseSettings):
    port: int
    secret_key: str
    debug: bool = False
    cors_origins: list[str] = []
    options: dict[str, int] = {}
    employee_no: str = "0001"
    llm_api_key: str = ""


class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdd-config-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        ConfigManager.reset()
        self.addCleanup(ConfigManager.reset)

    def write(self, content, name=".env"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_dotenv_quotes_types_and_no_environment_inheritance(self):
        path = self.write(
            "# file configuration\nexport PORT=8099\n"
            "SECRET_KEY='literal # value ${INJECTED_TEST_VALUE}'\n"
            "DEBUG=true\nEMPLOYEE_NO=0007\nLLM_API_KEY=\n"
            'CORS_ORIGINS=\'["http://localhost:5199"]\'\n'
            'OPTIONS=\'{"retries":2}\'\n'
        )
        with patch.dict(os.environ, {"PYCORE_PORT": "1", "PORT": "2",
                                     "INJECTED_TEST_VALUE": "from-process"}):
            before = dict(os.environ)
            settings = ConfigManager().load(Settings, path).settings
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(settings.port, 8099)
        self.assertEqual(settings.secret_key, "literal # value ${INJECTED_TEST_VALUE}")
        self.assertTrue(settings.debug)
        self.assertEqual(settings.cors_origins, ["http://localhost:5199"])
        self.assertEqual(settings.options, {"retries": 2})
        self.assertEqual(settings.employee_no, "0007")
        self.assertEqual(settings.llm_api_key, "")

    def test_explicit_environment_override_is_rejected(self):
        path = self.write("PORT=8099\nSECRET_KEY=test-only\n")
        with self.assertRaisesRegex(ConfigurationError, "overrides are disabled"):
            ConfigManager().load(Settings, path, use_env=True)

    def test_toml_profiles_remain_supported_without_environment_override(self):
        path = self.write('port=8099\nsecret_key="test-only"\n[dev]\nport=8003\n', "app.toml")
        with patch.dict(os.environ, {"PYCORE_PORT": "1"}):
            settings = ConfigManager().load(Settings, path, profile="dev").settings
        self.assertEqual(settings.port, 8003)
        self.assertEqual(settings.secret_key, "test-only")

    def test_dotenv_filename_variants(self):
        for name in (".env", ".env.local", "backend.env"):
            with self.subTest(name=name):
                path = self.write("PORT=8099\nSECRET_KEY=test-only\n", name)
                self.assertEqual(ConfigManager().load(Settings, path).settings.port, 8099)

    def test_missing_file_does_not_fall_back_to_environment(self):
        with patch.dict(os.environ, {"PYCORE_PORT": "8099", "PYCORE_SECRET_KEY": "test-only"}):
            with self.assertRaises(ConfigurationError):
                ConfigManager().load(Settings, self.root / ".env")

    def test_invalid_and_duplicate_entries_are_rejected_without_values(self):
        for text in ("SECRET_KEY='private-test-value", "SECRET_KEY", "PORT=1\nport=2"):
            with self.subTest(text=text):
                path = self.write(text)
                with self.assertRaises(ConfigurationError) as caught:
                    ConfigManager().load(Settings, path)
                self.assertNotIn("private-test-value", str(caught.exception))

    def test_validation_errors_do_not_expose_values(self):
        path = self.write("PORT=private-test-value\nSECRET_KEY=test-only\n")
        with self.assertRaises(ConfigurationError) as caught:
            ConfigManager().load(Settings, path)
        self.assertNotIn("private-test-value", str(caught.exception))
        with self.assertRaises(ConfigurationError) as caught:
            ConfigManager().load_from_dict(Settings, {"port": "private-test-value"})
        self.assertNotIn("private-test-value", str(caught.exception))

    def test_new_project_copy_uses_fixed_config_loader(self):
        project = self.root / "project"
        project.mkdir()
        copy_harness(project)
        (project / ".env").write_text("PORT=8099\n", encoding="utf-8")
        code = (
            "import json; from pycore.core.config import BaseSettings, ConfigManager; "
            "from pydantic import create_model; "
            "S=create_model('S',port=(int,...),__base__=BaseSettings); "
            "c=ConfigManager().load(S,'.env'); print(json.dumps({'port':c.settings.port}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=project, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(project), "PYTHONDONTWRITEBYTECODE": "1",
                 "PYCORE_PORT": "1"}, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"port": 8099})


if __name__ == "__main__":
    unittest.main()
