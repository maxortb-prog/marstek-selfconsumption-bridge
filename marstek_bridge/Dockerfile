ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TERM=xterm-256color

WORKDIR /

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
    io.hass.name="Marstek Self-consumption Bridge" \
    io.hass.description="Marstek for Self-consumption regulation (MQTT - UDP Bridge)" \
    io.hass.type="addon" \
    io.hass.version="0.0.4"

CMD [ "/run.sh" ]
