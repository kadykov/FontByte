FROM python:3.12-bookworm

WORKDIR /app

COPY requirements.txt /app/

RUN pip install -r requirements.txt --no-cache-dir

COPY github-filesize.py /app/

ENTRYPOINT [ "python", "/app/github-filesize.py" ]
