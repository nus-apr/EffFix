FROM yuntongzhang/infer:efffix

# install some basic software
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
    gdb \
    vim \
    wget \
    openssh-client

# install dependencies for benchmark programs
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
    libedit-dev \
    nasm \
    php \
    php7.4-dev \
    libpcap-dev \
    libpcre3 \
    libpcre3-dev \
    libdumbnet-dev \
    zlib1g-dev \
    libluajit-5.1-dev \
    libssl-dev \
    libnghttp2-dev \
    libdnet \
    openssl \
    bison \
    flex \
    libdaq-dev \
    clang-format \
    gettext \
    libtasn1-dev \
    libffi-dev \
    autopoint \
    texinfo \
    help2man \
    bc \
    gcc \
    clang \
    libssl-dev \
    libelf-dev

# clone the benchmark repo
WORKDIR /opt
RUN git clone https://github.com/nus-apr/effFix-benchmark.git

# install python dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
    python3-pip \
    swig \
    python-dev \
    python3-dev \
    python3-dbg
RUN python3 -m pip install pysmt z3-solver z3 networkx matplotlib
RUN python3 -m pip install --upgrade networkx
RUN python3 -m pysmt install --confirm-agreement --z3
RUN python3 -m pysmt install --confirm-agreement --cvc4

# Download codeql v2.12.2
WORKDIR /opt
RUN wget https://github.com/github/codeql-cli-binaries/releases/download/v2.12.2/codeql-linux64.zip
RUN unzip codeql-linux64.zip
ENV PATH="${PATH}:/opt/codeql/"

# update to the latest modifed Infer and rebuilt
WORKDIR /opt/infer
RUN git stash && git checkout main && git pull origin main
WORKDIR /opt/infer/infer/src
RUN make BUILD_MODE=dev-noerror -j16

# copy src files of the tool
COPY . /opt/EffFix/

# install codeql dependencies for our queries
WORKDIR /opt/EffFix/codeql
RUN codeql pack install

# set git url
WORKDIR /opt/EffFix/
RUN git remote rm origin
RUN git remote add origin https://github.com/nus-apr/EffFix.git

# for debugging
COPY ./vimrc /root/.vimrc

# update benchmark directory content, just in case
WORKDIR /opt/effFix-benchmark
RUN git stash && git checkout main && git pull origin main

# set paths
ENV PATH /opt/EffFix:/opt/infer/infer/bin:${PATH}
ENV PYTHONPATH /opt/EffFix:${PYTHONPATH}

WORKDIR /opt/EffFix/
ENTRYPOINT /bin/bash
