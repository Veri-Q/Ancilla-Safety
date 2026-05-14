FROM python:3.11-slim AS gpmc-builder

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /tmp/GPMC

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        make \
        libgmp-dev \
        libmpfr-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/GPMC /tmp/GPMC

RUN sh ./build.sh r \
    && mkdir -p /opt/gpmc/bin \
    && cp bin/gpmc /opt/gpmc/bin/gpmc

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV MPLBACKEND=Agg
ENV GPMC_PATH=/opt/gpmc/bin/gpmc
ENV PYTHONPATH=/workspace:/workspace/quokka_sharp

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgmp10 \
        libgmpxx4ldbl \
        libmpfr6 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies used by the artifact runners and backends.
RUN pip install --no-cache-dir \
    matplotlib \
    mqt.qcec \
    numpy \
    qiskit

COPY --from=gpmc-builder /opt/gpmc/bin/gpmc /opt/gpmc/bin/gpmc

COPY . /workspace

RUN pip install --no-cache-dir ./quokka_sharp

RUN chmod +x \
    /workspace/run_kick_the_tires.sh \
    /workspace/run_all_experiments.sh \
    /workspace/run_table1.sh \
    /workspace/run_table2.sh \
    /workspace/run_figure3.sh \
    /workspace/run_table3.sh \
    /workspace/docker-entrypoint.sh

ENTRYPOINT ["/workspace/docker-entrypoint.sh"]
CMD ["/bin/bash"]
