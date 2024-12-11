FROM python:3.12-bookworm

RUN apt-get update \
&& apt-get install -y curl \
&& rm -rf /var/lib/apt/lists/* \
&& curl -L $(curl https://quarto.org/docs/download/_prerelease.json | grep -oP "(?<=\"download_url\":\s\")https.*${ARCH}\.deb") -o /tmp/quarto.deb \
&& dpkg -i /tmp/quarto.deb \
&& rm /tmp/quarto.deb

WORKDIR /data/

COPY requirements.txt /data/

RUN pip install -r requirements.txt --no-cache-dir

ENTRYPOINT [ "quarto", "render", "." ]
