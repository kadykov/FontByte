# %%
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pandas as pd
from github import Auth, Github, Repository
from IPython.display import HTML
from itables import to_html_datatable


@dataclass
class Font:
    repo: Repository
    path: str

    @lru_cache
    def get_metadata(self) -> dict[str, Any]:
        contents = self.repo.get_contents(f"{self.path}/metadata.json")
        return json.loads(contents.decoded_content)

    def _generate_filename(self, subset=None, variable="wght", style="normal") -> str:
        metadata = self.get_metadata()
        id = metadata["id"]
        if not subset:
            subset = metadata["defSubset"]
        return f"{id}-{subset}-{variable}-{style}.woff2"

    def get_filesize(self, subset=None, variable="wght", style="normal") -> int | None:
        filename = self._generate_filename(
            subset=subset, variable=variable, style=style
        )
        return self._get_filesizes().get(filename)

    @lru_cache
    def _get_filesizes(self) -> dict[str, int]:
        contents = self.repo.get_contents(path=f"{self.path}/files")
        return {content.name: content.size for content in contents}

    def get_family(self) -> str:
        return self.get_metadata()["family"]

    def get_variables(self) -> dict[str, dict]:
        return self.get_metadata()["variable"]

    def get_category(self) -> str:
        category = self.get_metadata()["category"]
        if category.startswith("sans-"):
            return "sans"
        return category

    def get_subsets(self) -> list[str]:
        return self.get_metadata()["subsets"]

    def get_styles(self) -> list[str]:
        return self.get_metadata()["styles"]

    def get_url(self) -> str:
        id = self.get_metadata()["id"]
        return f"https://fontsource.org/fonts/{id}"

    def __hash__(self):
        return hash(f"{self.repo.__hash__()}{self.path}")


os.environ["GITHUB_TOKEN"]

auth = Auth.Token(os.environ["GITHUB_TOKEN"])
g = Github(auth=auth)

repo = g.get_repo("fontsource/font-files")
contents = repo.get_contents("fonts/variable")

font_names = [content.name for content in contents]
# %%
sizes = {}
categories = {}
subsets = {}
styles = {}
variables = {}
for font_name in font_names:
    font = Font(repo=repo, path=f"fonts/variable/{font_name}")
    print(font.get_family())
    if ("latin" in font.get_subsets()) and (
        "wght" in font.get_variables() and font.get_filesize()
    ):
        family = font.get_family()
        linked_family = f'<a href="{font.get_url()}">{family}</a>'
        sizes[linked_family] = font.get_filesize()
        categories[linked_family] = font.get_category()
        subsets[linked_family] = font.get_subsets()
        styles[linked_family] = font.get_styles()
        variables[linked_family] = font.get_variables().keys()

# %%
df = pd.DataFrame.from_dict(
    {
        "Latin file size [bytes]": sizes,
        "Category": categories,
        "Subsets": subsets,
        "Style": styles,
        "Variables": variables,
    }
)
# %%
html = to_html_datatable(
    df.sort_values("Latin file size [bytes]"),
    display_logo_when_loading=False,
    layout={
        "topStart": "search",
        "topEnd": "pageLength",
        "bottomStart": "paging",
        "bottomEnd": "info",
    },
    column_filters="footer",
    lengthMenu=[10, 25, 50, 100, 250, 500],
)

with open("index.html", "w") as table:
    table.write(HTML(html).data)

# %%
