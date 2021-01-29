FROM registry.redhat.io/ubi8:latest
  
MAINTAINER Nate Stephany <nate@redhat.com>

USER root

RUN yum install -y python38 && yum clean all

COPY ./cleanup/ /app/

RUN python3 -m pip install -r /app/requirements.txt

USER 1001

CMD ["/app/check_account.py"]

ENTRYPOINT ["python3"]