import argparse
import logging
import sys
import os

from kubernetes import client, config
from kubernetes.client import rest

#from .watcher import *


class simpleauth():
    def __init__(self, sslCertPath=None, jwtTOKEN=None, **kwargs):
        self.sslCertPath = sslCertPath
        self.jwtTOKEN = jwtTOKEN
        self.kwargs = kwargs


        # create an instance of the API class
        authConfiguration = client.Configuration()

         # Logging Settings
        #authConfiguration.logger = {}
        #authConfiguration.logger["package_logger"] = logging.getLogger("client")

        #authConfiguration = None
        #authConfiguration.verify_ssl = False
        #authConfiguration.api_key_prefix['attribute'] = 'default_headers'
        #authConfiguration.api_key["attribute"] = 'yes'

        #authConfiguration.ssl_ca_cert = os.getenv('PATH_TO_CA_PEM')
        authConfiguration.api_key_prefix['authorization'] = 'Bearer'
        authConfiguration.api_key["authorization"] = jwtTOKEN
        self.authConfiguration = authConfiguration


def process_kubeconfig():
        if 'KUBERNETES_PORT' in os.environ:
        config.load_incluster_config()
    else:
        config.load_kube_config()



def create_authorized_client(sslCertPath=None, jwtTOKEN=None, **kwargs):
    authConfiguration = client.Configuration()

    if (os.getenv('JWT_ENABLE') != ""):
        try:
            jwt = os.getenv('JWT_TOKEN')
        except:
            try:
                file = open("/var/run/secrets/kubernetes.io/serviceaccount/token")
                jwt = file.read()
                print("JWT: " + jwt)
            except:
                jwt=""
        
        authConfiguration.api_key_prefix['authorization'] = 'Bearer'
        authConfiguration.api_key["authorization"] = jwtTOKEN
    
    #authConfiguration.logger = {}
    #authConfiguration.logger["package_logger"] = logging.getLogger("client")

    #authConfiguration = None
    #authConfiguration.verify_ssl = False
    #authConfiguration.api_key_prefix['attribute'] = 'default_headers'
    #authConfiguration.api_key["attribute"] = 'yes'

    #authConfiguration.ssl_ca_cert = os.getenv('PATH_TO_CA_PEM')

    authorizedClient = client.ApiClient(authConfiguration)

    return authorizedClient

def create_api_client(apiVersion, authClient, **kwargs):

    app_watcher_api = client.CoreV1Api(authClient)
    pod_api = client.CoreV1Api(authClient)


    #WatcherOperatorConfig "Master" Configuration (Could be configmap, secret, helm values, etc.)
    #Change into CRD, run an "install Pod" to do upgrades, installs, etc.

    #LOad "App COnfig"
    namespace = "watch-this"
    event_filter_list = ['ADDED','MODIFIED','DELETED']
    pApi = "CoreV1Api"
    pResource = "list_namespaced_service"
    api = eval('client.' + apiVersion + '(authClient)')
    
    return apiClient