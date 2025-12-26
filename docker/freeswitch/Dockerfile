FROM debian:bullseye-slim

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    cmake \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    libdb-dev \
    libncurses5-dev \
    libexpat1-dev \
    libgdbm-dev \
    bison \
    libbison-dev \
    libcurl4-openssl-dev \
    libspeex-dev \
    libspeexdsp-dev \
    libldns-dev \
    libedit-dev \
    libpcre3-dev \
    libsqlite3-dev \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone FreeSWITCH
WORKDIR /usr/src
RUN git clone https://github.com/signalwire/freeswitch.git freeswitch
WORKDIR /usr/src/freeswitch

# Checkout stable version
RUN git checkout v1.10.11

# Bootstrap and configure
RUN ./bootstrap.sh -j
RUN ./configure --disable-debug --disable-libyuv --enable-core-pgsql-support

# Build (this will take 15-20 minutes)
RUN make -j$(nproc)
RUN make install

# Create runtime directories
RUN mkdir -p /usr/local/freeswitch/recordings
RUN mkdir -p /var/run/freeswitch

# Expose ports
EXPOSE 5060/tcp 5060/udp 5080/tcp 5080/udp 8021/tcp 16384-32768/udp

# Run FreeSWITCH
CMD ["/usr/local/freeswitch/bin/freeswitch", "-nonat", "-nc"]
