# Dockerfile
FROM ubuntu:focal
RUN apt-get update -q

RUN apt-get install -y ssh
RUN apt-get install -y python3
RUN apt-get install -y python3-pip
RUN apt-get install -y git
RUN apt-get install -y make
RUN pip3 install -U sphinx
RUN apt-get install -y libxml2-dev

RUN mkdir /app
WORKDIR /app
Add . /app
