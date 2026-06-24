import asyncio
import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "github_filesize.py"
spec = importlib.util.spec_from_file_location("github_filesize", MODULE_PATH)
if spec is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
module = importlib.util.module_from_spec(spec)
if spec.loader is None:
    raise RuntimeError(f"Unable to create loader for {MODULE_PATH}")
spec.loader.exec_module(module)
github_filesize = module


class MainFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_does_not_log_when_limit_is_zero(self):
        with (
            patch("builtins.print") as mock_print,
            patch.object(
                github_filesize,
                "get_font_names",
                new=AsyncMock(return_value=["font-a"]),
            ),
            patch.object(github_filesize, "get_max_fonts", return_value=0),
            patch.object(
                github_filesize, "create_font_table", new=AsyncMock()
            ) as mock_create_table,
            patch.object(github_filesize, "write_index_page") as mock_write_index,
        ):
            await github_filesize.main()

        mock_print.assert_not_called()
        self.assertEqual(mock_create_table.await_count, len(github_filesize.axes))
        mock_write_index.assert_called_once_with()

    async def test_main_logs_and_limits_font_names_when_limit_is_positive(self):
        with (
            patch("builtins.print") as mock_print,
            patch.object(
                github_filesize,
                "get_font_names",
                new=AsyncMock(return_value=["font-a", "font-b", "font-c"]),
            ),
            patch.object(github_filesize, "get_max_fonts", return_value=2),
            patch.object(
                github_filesize, "create_font_table", new=AsyncMock()
            ) as mock_create_table,
            patch.object(github_filesize, "write_index_page") as mock_write_index,
        ):
            await github_filesize.main()

        self.assertEqual(mock_print.call_count, 1)
        self.assertIn("Limiting font processing to 2 fonts", mock_print.call_args[0][0])
        self.assertEqual(
            mock_create_table.await_args_list[0].args[0],
            ["font-a", "font-b"],
        )
        self.assertEqual(mock_create_table.await_count, len(github_filesize.axes))
        mock_write_index.assert_called_once_with()


class GithubFilesizeHelpersTest(unittest.TestCase):
    def test_limits_font_names_when_configured(self):
        font_names = [f"font-{index}" for index in range(12)]

        limited = github_filesize.limit_font_names(font_names, max_fonts=5)

        self.assertEqual(limited, [f"font-{index}" for index in range(5)])

    def test_returns_all_when_limit_is_disabled(self):
        font_names = ["font-a", "font-b"]

        self.assertEqual(
            github_filesize.limit_font_names(font_names, max_fonts=None), font_names
        )
        self.assertEqual(
            github_filesize.limit_font_names(font_names, max_fonts=0), font_names
        )

    def test_reads_limit_from_environment(self):
        with patch.dict(os.environ, {"MAX_FONTS": "3"}, clear=False):
            self.assertEqual(github_filesize.get_max_fonts(), 3)

    def test_resolve_output_path_uses_output_dir_environment(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}, clear=False):
                output_path = github_filesize.resolve_output_path("index.html")

            self.assertEqual(output_path, Path(temp_dir) / "index.html")

    def test_rejects_negative_environment_limit(self):
        with patch.dict(os.environ, {"MAX_FONTS": "-1"}, clear=False):
            with self.assertRaises(ValueError):
                github_filesize.get_max_fonts()

    def test_reads_integer_environment_variables(self):
        with patch.dict(os.environ, {"MAX_CONCURRENT_REQUESTS": "7"}, clear=False):
            self.assertEqual(
                github_filesize.get_int_env("MAX_CONCURRENT_REQUESTS", 5), 7
            )

    def test_initialize_runtime_creates_request_lock(self):
        original_request_lock = github_filesize.request_lock
        original_runtime_initialized = github_filesize._runtime_initialized
        try:
            with (
                patch.object(github_filesize, "_runtime_initialized", False),
                patch.object(github_filesize, "load_dotenv") as mock_load_dotenv,
                patch.object(github_filesize.nest_asyncio, "apply") as mock_apply,
                patch.object(github_filesize, "get_int_env", side_effect=[1, 1]),
            ):
                github_filesize.request_lock = None
                github_filesize.request_semaphore = None
                github_filesize.request_times = []
                github_filesize.initialize_runtime()
                self.assertIsInstance(github_filesize.request_lock, asyncio.Lock)

            mock_load_dotenv.assert_called_once_with()
            mock_apply.assert_called_once_with()
        finally:
            github_filesize.request_lock = original_request_lock
            github_filesize._runtime_initialized = original_runtime_initialized

    def test_rejects_non_integer_environment_variables(self):
        with patch.dict(os.environ, {"MAX_CONCURRENT_REQUESTS": "abc"}, clear=False):
            with self.assertRaises(ValueError):
                github_filesize.get_int_env("MAX_CONCURRENT_REQUESTS", 5)

    def test_rejects_non_positive_environment_variables(self):
        with patch.dict(os.environ, {"MAX_CONCURRENT_REQUESTS": "0"}, clear=False):
            with self.assertRaises(ValueError):
                github_filesize.get_int_env("MAX_CONCURRENT_REQUESTS", 5, minimum=1)

    def test_returns_none_when_github_token_is_missing(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            self.assertIsNone(github_filesize.get_github_token())

    def test_requires_github_token_when_missing(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                github_filesize.require_github_token()

    def test_rate_limit_wait_requires_runtime_initialization(self):
        with (
            patch.object(github_filesize, "initialize_runtime", return_value=None),
            patch.object(github_filesize, "request_semaphore", None),
            patch.object(github_filesize, "request_times", []),
            patch.object(github_filesize, "REQUESTS_PER_MINUTE", 1),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(github_filesize.rate_limit_wait())

    def test_get_reset_delay_uses_safe_default_for_invalid_values(self):
        class DummyRateLimitExceeded(Exception):
            reset_in = "invalid"

        self.assertEqual(github_filesize.get_reset_delay(DummyRateLimitExceeded()), 60)


if __name__ == "__main__":
    unittest.main()
