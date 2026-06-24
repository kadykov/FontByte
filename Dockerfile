FROM python:3.12-bookworm

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY github_filesize.py /app/

RUN pip install --no-cache-dir .

ENTRYPOINT [ "python", "-m", "github_filesize" ]
