import sys
import types
import unittest
from unittest import mock

import app
from app import __main__ as launcher


class PackageEntrypointTests(unittest.TestCase):
    def test_version_is_available_without_starting_the_gui(self):
        self.assertEqual(app.__version__, "0.1.0.dev0")

    def test_module_launcher_delegates_to_application_main(self):
        run_application = mock.Mock()
        fake_main_module = types.ModuleType("app.main_v3")
        fake_main_module.main = run_application
        with mock.patch.dict(sys.modules, {"app.main_v3": fake_main_module}):
            launcher.main()
        run_application.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
