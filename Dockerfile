# SPDX-License-Identifier: GPL-3.0-or-later
# Picturestation in Docker / Synology Container Manager.
#   docker run -d --name picturestation -p 8080:8080 \
#     -v /volume1/photo:/photos:ro -v /volume1/docker/picturestation:/data \
#     ghcr.io/valdaaak/picturestation
FROM debian:trixie-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-starlette python3-uvicorn python3-pil \
      ffmpeg sqlite3 ca-certificates wget unzip \
 && rm -rf /var/lib/apt/lists/*

COPY server/picturestation /opt/picturestation/picturestation
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/picturestation-user /usr/local/bin/picturestation-user
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/picturestation-user \
 && find /opt/picturestation -name __pycache__ -prune -exec rm -rf {} +

ENV PYTHONPATH=/opt/picturestation \
    PYTHONUNBUFFERED=1 \
    PICTURESTATION_ROOT=/photos \
    PICTURESTATION_DATA=/data \
    PICTURESTATION_PORT=8080 \
    PICTURESTATION_INDEX_INTERVAL=1800 \
    PUID=1000 \
    PGID=1000

VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/' % os.environ.get('PICTURESTATION_PORT', '8080'), timeout=4)"
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
