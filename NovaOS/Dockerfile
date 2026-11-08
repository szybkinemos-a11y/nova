# NovaOS – powtarzalne środowisko budowania ISO (działa na każdym Linuksie z Dockerem/Podmanem)
FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin grub-common \
        mtools dosfstools rsync librsvg2-bin fonts-inter python3 git ca-certificates \
        dpkg-dev shellcheck python3-yaml python3-jsonschema python3-pytest \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /novaos
ENTRYPOINT ["/novaos/scripts/build-iso.sh"]
