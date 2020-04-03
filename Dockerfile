FROM bitnami/python:3.7-prod
USER 0

# Define Env Variables
ENV TEST="working1"

# setup resource directories
RUN mkdir -p /app /config

COPY requirements.txt /
RUN pip install -r requirements.txt

# copy resources
COPY . /
#COPY ./image-data-reporting/config/* /config/
#COPY ./image-data-reporting/requirements.txt /

# change workdir
WORKDIR /

# install


# setup kubeconfig parts
#ARG kube_config_location=/config/kube.config
#ENV KUBECONFIG=$kube_config_location

# setup the config location
#ARG config_location=/config/config.ini
#ENV CONFIG_LOCATION=$config_location

# setup the google credentials part
#ARG google_application_credentials=/config/credentials.json
#ENV GOOGLE_APPLICATION_CREDENTIALS=$google_application_credentials

USER 1234

# setup the entrypoint
ENTRYPOINT ["python3","-m","app"]