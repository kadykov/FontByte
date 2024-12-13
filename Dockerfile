FROM python:3.12-bookworm

WORKDIR /data/

COPY requirements.txt /data/

RUN pip install -r requirements.txt --no-cache-dir

ENTRYPOINT [ "python", "./github-filesize.py" ]
