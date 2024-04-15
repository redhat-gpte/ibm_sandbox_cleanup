FROM registry.access.redhat.com/ubi9/python-311:latest
  
MAINTAINER Nate Stephany <nate@redhat.com>

USER 0

COPY cleanup/ /tmp/src

RUN chown -R 1001 /tmp/src && \
    chgrp -R 0 /tmp/src && \
    chmod -R g+w /tmp/src

USER 1001

RUN /usr/libexec/s2i/assemble

CMD ["/usr/libexec/s2i/run"]
