# %%
import asyncio
import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

import aiohttp
import nest_asyncio
import pandas as pd
from gidgethub import RateLimitExceeded
from gidgethub.aiohttp import GitHubAPI
from IPython.display import HTML
from itables import to_html_datatable

load_dotenv()
nest_asyncio.apply()

# GitHub API limits
MAX_CONCURRENT_REQUESTS = 50  # Keep well below the 100 limit
REQUESTS_PER_MINUTE = 800  # Keep below 900 to have some buffer

# Create a semaphore to limit concurrent requests
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Track request times for rate limiting
request_times: list[float] = []


async def rate_limit_wait():
    """Wait if we're exceeding the rate limit."""
    now = time.time()
    # Remove requests older than 1 minute
    while request_times and request_times[0] < now - 60:
        request_times.pop(0)
    # If we're at the limit, wait until we have capacity
    if len(request_times) >= REQUESTS_PER_MINUTE:
        wait_time = request_times[0] - (now - 60)
        if wait_time > 0:
            print(f"Rate limit reached, waiting {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time)
    request_times.append(now)


async def github_request(gh: GitHubAPI, url: str) -> Any:
    """Make a GitHub API request with rate limiting and retries."""
    async with request_semaphore:
        while True:
            try:
                await rate_limit_wait()
                return await gh.getitem(url)
            except RateLimitExceeded as e:
                # Wait until rate limit resets
                print(f"Rate limit exceeded, waiting {e.reset_in} seconds...")
                await asyncio.sleep(e.reset_in)
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
            oauth_token=os.environ["GITHUB_TOKEN"],
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
            oauth_token=os.environ["GITHUB_TOKEN"],
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
            lengthMenu=[10, 25, 50, 100, 250, 500],
            allow_html=True,
        )

        with open(output_file, "w") as table:
            table.write(HTML(html).data)


# Create tables for different axes
axes = ["wght", "opsz", "wdth"]


# Generate tables for each axis
async def main():
    # Get font names first
    font_names = await get_font_names()

    # Process each axis in parallel
    async with asyncio.TaskGroup() as tg:
        for axis in axes:
            tg.create_task(create_font_table(font_names, axis, f"{axis}.html"))


# Run the async main function
asyncio.run(main())

# Create index.html with links to all tables
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

# Add a link and description for each axis
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

with open("index.html", "w") as f:
    f.write(index_html)

# %%
