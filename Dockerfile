FROM python:3.12-bookworm

WORKDIR /data/

COPY requirements.txt /data/

RUN pip install -r requirements.txt --no-cache-dir

RUN mkdir -p /home/vscode/.vscode-server/data/User/globalStorage

ENTRYPOINT [ "python", "./github-filesize.py" ]
