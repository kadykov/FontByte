# %%
import asyncio
import base64
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
import nest_asyncio
import pandas as pd
from dotenv import load_dotenv
from gidgethub import RateLimitExceeded
from gidgethub.aiohttp import GitHubAPI
from IPython.display import HTML
from itables import to_html_datatable

_runtime_initialized = False


def initialize_runtime() -> None:
    global \
        MAX_CONCURRENT_REQUESTS, \
        REQUESTS_PER_MINUTE, \
        request_semaphore, \
        request_times, \
        request_lock
    global _runtime_initialized

    if _runtime_initialized:
        return

    load_dotenv()
    nest_asyncio.apply()

    MAX_CONCURRENT_REQUESTS = get_int_env("MAX_CONCURRENT_REQUESTS", 10, minimum=1)
    REQUESTS_PER_MINUTE = get_int_env("REQUESTS_PER_MINUTE", 120, minimum=1)
    request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    request_times = []
    request_lock = asyncio.Lock()
    _runtime_initialized = True


def get_int_env(
    name: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
    raw_value: str | None = None,
) -> int:
    value = raw_value if raw_value is not None else os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc

    if minimum is not None and parsed_value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {parsed_value}")
    if maximum is not None and parsed_value > maximum:
        raise ValueError(f"{name} must be at most {maximum}, got {parsed_value}")
    return parsed_value


def get_github_token() -> str | None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    return token or None


def require_github_token() -> str:
    token = get_github_token()
    if token is None:
        raise RuntimeError("GITHUB_TOKEN must be set to query GitHub font metadata.")
    return token


# GitHub API limits
MAX_CONCURRENT_REQUESTS = 10
REQUESTS_PER_MINUTE = 120
request_semaphore: asyncio.Semaphore | None = None
request_times: list[float] = []
request_lock: asyncio.Lock | None = None


def limit_font_names(font_names: list[str], max_fonts: int | None = None) -> list[str]:
    """Limit the number of fonts processed for local or CI runs."""
    if max_fonts is None or max_fonts <= 0:
        return font_names
    return font_names[:max_fonts]


def get_max_fonts() -> int | None:
    raw_value = os.getenv("MAX_FONTS", "").strip()
    if not raw_value:
        return None
    return get_int_env("MAX_FONTS", 0, minimum=0, raw_value=raw_value)


async def rate_limit_wait():
    """Wait if we're exceeding the rate limit."""
    initialize_runtime()
    if request_semaphore is None:
        raise RuntimeError("request_semaphore is not initialized")

    if request_lock is None:
        raise RuntimeError("request_lock is not initialized")

    now = time.time()
    async with request_lock:
        # Remove requests older than 1 minute
        while request_times and request_times[0] < now - 60:
            request_times.pop(0)
        # If we're at the limit, wait until we have capacity
        if len(request_times) >= REQUESTS_PER_MINUTE:
            wait_time = request_times[0] - (now - 60)
            if wait_time > 0:
                print(f"Rate limit reached, waiting {wait_time:.1f} seconds...")
                await asyncio.sleep(wait_time)
                now = time.time()
        request_times.append(now)


def get_reset_delay(error: RateLimitExceeded) -> int:
    raw_reset = getattr(error, "reset_in", None)
    if raw_reset is None:
        return 60
    try:
        reset_in = math.ceil(float(raw_reset))
    except (TypeError, ValueError):
        return 60
    return max(reset_in, 1)


async def github_request(gh: GitHubAPI, url: str) -> Any:
    """Make a GitHub API request with rate limiting and retries."""
    initialize_runtime()
    if request_semaphore is None:
        raise RuntimeError("request_semaphore is not initialized")

    async with request_semaphore:
        while True:
            try:
                await rate_limit_wait()
                return await gh.getitem(url)
            except RateLimitExceeded as error:
                reset_in = get_reset_delay(error)
                print(f"Rate limit exceeded, waiting {reset_in} seconds...")
                await asyncio.sleep(reset_in)
                continue


@dataclass
class Font:
    gh: GitHubAPI
    owner: str
    repo: str
    path: str
    _metadata_cache: dict[str, Any] | None = None
    _filesizes_cache: dict[str, int] | None = None

    async def get_metadata(self) -> dict[str, Any]:
        if self._metadata_cache is None:
            response = await github_request(
                self.gh,
                f"/repos/{self.owner}/{self.repo}/contents/{self.path}/metadata.json",
            )
            content = base64.b64decode(response["content"]).decode("utf-8")
            self._metadata_cache = json.loads(content)
        if self._metadata_cache is None:
            raise RuntimeError("metadata cache was not initialized")
        return self._metadata_cache

    async def _generate_filename(
        self, subset=None, variable="wght", style="normal"
    ) -> str:
        metadata = await self.get_metadata()
        id = metadata["id"]
        if not subset:
            subset = metadata["defSubset"]
        return f"{id}-{subset}-{variable}-{style}.woff2"

    async def get_filesize(
        self, subset=None, variable="wght", style="normal"
    ) -> int | None:
        filename = await self._generate_filename(
            subset=subset, variable=variable, style=style
        )
        filesizes = await self._get_filesizes()
        return filesizes.get(filename)

    async def _get_filesizes(self) -> dict[str, int]:
        if self._filesizes_cache is None:
            response = await github_request(
                self.gh, f"/repos/{self.owner}/{self.repo}/contents/{self.path}/files"
            )
            self._filesizes_cache = {item["name"]: item["size"] for item in response}
        return self._filesizes_cache

    async def get_family(self) -> str:
        metadata = await self.get_metadata()
        return metadata["family"]

    async def get_variables(self) -> dict[str, dict]:
        metadata = await self.get_metadata()
        return metadata["variable"]

    async def get_category(self) -> str:
        metadata = await self.get_metadata()
        category = metadata["category"]
        if category.startswith("sans-"):
            return "sans"
        return category

    async def get_subsets(self) -> list[str]:
        metadata = await self.get_metadata()
        return metadata["subsets"]

    async def get_styles(self) -> list[str]:
        metadata = await self.get_metadata()
        return metadata["styles"]

    async def get_url(self) -> str:
        metadata = await self.get_metadata()
        id = metadata["id"]
        return f"https://fontsource.org/fonts/{id}"

    def __hash__(self):
        return hash(f"{self.owner}/{self.repo}/{self.path}")


async def get_font_names() -> list[str]:
    async with aiohttp.ClientSession() as session:
        gh = GitHubAPI(
            session,
            "openhands",
            oauth_token=require_github_token(),
        )
        response = await github_request(
            gh, "/repos/fontsource/font-files/contents/fonts/variable"
        )
        return [item["name"] for item in response]  # [:10]  # Limit to 10 fonts


# %%
async def process_font(
    gh: GitHubAPI, font_name: str, axis: str
) -> tuple[str, dict] | None:
    font = Font(
        gh=gh, owner="fontsource", repo="font-files", path=f"fonts/variable/{font_name}"
    )
    subsets = await font.get_subsets()
    variables = await font.get_variables()
    filesize = await font.get_filesize(variable=axis)

    if ("latin" in subsets) and (axis in variables and filesize):
        family = await font.get_family()
        url = await font.get_url()
        linked_family = f'<a href="{url}">{family}</a>'
        print(family)

        return linked_family, {
            "size": filesize,
            "category": await font.get_category(),
            "subsets": subsets,
            "styles": await font.get_styles(),
            "variables": variables.keys(),
        }
    return None


async def create_font_table(font_names: list[str], axis: str, output_file: str) -> None:
    async with aiohttp.ClientSession() as session:
        gh = GitHubAPI(
            session,
            "openhands",
            oauth_token=require_github_token(),
        )

        # Process fonts in parallel with TaskGroup
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(process_font(gh, font_name, axis))
                for font_name in font_names
            ]
        # All tasks are complete when we exit the context manager
        results = [task.result() for task in tasks]

        sizes = {}
        categories = {}
        subsets = {}
        styles = {}
        variables = {}

        for result in results:
            if result:
                linked_family, data = result
                sizes[linked_family] = data["size"]
                categories[linked_family] = data["category"]
                subsets[linked_family] = data["subsets"]
                styles[linked_family] = data["styles"]
                variables[linked_family] = data["variables"]

        df = pd.DataFrame.from_dict(
            {
                f"Latin file size [{axis}] [bytes]": sizes,
                "Category": categories,
                "Subsets": subsets,
                "Style": styles,
                "Variables": variables,
            }
        )

        html = to_html_datatable(
            df.sort_values(f"Latin file size [{axis}] [bytes]"),
            display_logo_when_loading=False,
            layout={
                "topStart": "search",
                "topEnd": "pageLength",
                "bottomStart": "paging",
                "bottomEnd": "info",
            },
            column_filters="footer",
            lengthMenu=[25, 50, 100, 250, 500],
            allow_html=True,
            showIndex=True,
            buttons=["columnsToggle"],
        )

        with open(output_file, "w", encoding="utf-8") as table:
            table.write(str(HTML(html).data or ""))


# Create tables for different axes
axes = ["wght", "opsz", "wdth"]


# Generate tables for each axis
async def main():
    initialize_runtime()
    font_names = await get_font_names()
    max_fonts = get_max_fonts()
    if max_fonts is not None and max_fonts > 0:
        print(
            f"Limiting font processing to {max_fonts} fonts because MAX_FONTS is set."
        )
        font_names = limit_font_names(font_names, max_fonts=max_fonts)

    async with asyncio.TaskGroup() as tg:
        for axis in axes:
            tg.create_task(create_font_table(font_names, axis, f"{axis}.html"))

    write_index_page()


def write_index_page() -> None:
    index_html = """<!DOCTYPE html>
<html>
<head>
    <title>Variable Font Size Tables</title>
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            max-width: 800px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        h1 { margin-bottom: 2rem; }
        .axis-list {
            list-style: none;
            padding: 0;
        }
        .axis-list li {
            margin: 1rem 0;
        }
        .axis-list a {
            display: block;
            padding: 1rem;
            background: #f0f0f0;
            border-radius: 0.5rem;
            text-decoration: none;
            color: #333;
            font-size: 1.1rem;
        }
        .axis-list a:hover {
            background: #e0e0e0;
        }
        .axis-name {
            font-weight: bold;
        }
        .axis-desc {
            color: #666;
            font-size: 0.9rem;
            margin-top: 0.3rem;
        }
    </style>
</head>
<body>
    <h1>Variable Font Size Tables</h1>
    <ul class="axis-list">"""

    axis_descriptions = {
        "wght": "Weight axis - controls the thickness of the font strokes",
        "opsz": "Optical Size axis - optimizes the design for different sizes",
        "wdth": "Width axis - adjusts the horizontal proportions",
    }

    for axis in axes:
        index_html += f"""
        <li>
            <a href="{axis}.html">
                <div class="axis-name">{axis.upper()} Axis</div>
                <div class="axis-desc">{axis_descriptions[axis]}</div>
            </a>
        </li>"""

    index_html += """
    </ul>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(index_html)


if __name__ == "__main__":
    asyncio.run(main())

# %%
