# %%
from dataclasses import dataclass
from typing import Any
from functools import lru_cache

import requests  # type: ignore


@dataclass
class Repository:
    repo_owner: str
    repo_name: str
    branch: str = "main"

    def _get_data(self, path: str) -> list[dict[str, Any]] | dict[str, Any]:
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{path}?ref={self.branch}"
        response = requests.get(api_url)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(
                f"Error: Unable to fetch files. Status code: {response.status_code}"
            )

    def get_foldernames(self, path: str) -> list[str]:
        data = self._get_data(path=path)
        if type(data) is list:
            return [file["name"] for file in data if file["type"] == "dir"]
        raise Exception("Not a directory")

    def get_filesizes(self, path: str) -> dict[str, int]:
        data = self._get_data(path=path)
        if type(data) is list:
            return {
                file["name"]: file["size"] for file in data if file["type"] == "file"
            }
        raise Exception("Not a directory")

    def get_file(self, path: str) -> Any:
        data = self._get_data(path=path)
        if type(data) is dict:
            response = requests.get(data["download_url"])

            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(
                    f"Error: Unable to fetch files. Status code: {response.status_code}"
                )
        raise Exception("Not a directory")

    def __hash__(self) -> int:
        return hash(f"{self.repo_owner}{self.repo_name}{self.branch}")


@dataclass
class Font:
    repo: Repository
    path: str

    @lru_cache
    def get_metadata(self) -> dict[str, Any]:
        return self.repo.get_file(path=f"{self.path}/metadata.json")

    def _generate_filename(self) -> str:
        metadata = self.get_metadata()
        id = metadata["id"]
        subset = metadata["defSubset"]
        # variables = metadata["variable"].keys()
        return f"{id}-{subset}-wght-normal.woff2"

    def get_filesize(self) -> int:
        sizes = self.repo.get_filesizes(path=f"{self.path}/files/")
        return sizes[self._generate_filename()]

    def __hash__(self):
        return hash(f"{self.repo.__hash__()}{self.path}")


repo = Repository("fontsource", "font-files")
font_names = repo.get_foldernames("fonts/variable/")
font = Font(repo=repo, path=f"fonts/variable/{font_names[0]}")
font.get_metadata()
font.get_filesize()
# repo.get_filesizes(f"fonts/variable/{font_names[0]}/files")
# repo.get_file(f"fonts/variable/{font_names[0]}/metadata.json")

# %%
