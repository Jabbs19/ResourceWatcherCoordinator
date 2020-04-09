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


def load_cluster_config():
    if 'KUBERNETES_PORT' in os.environ:
        config.load_incluster_config()
    else:
        config.load_kube_config()



def create_authorized_client(sslCertPath=None, jwtTOKEN=None, **kwargs):
    authConfiguration = client.Configuration()

    if (os.getenv('JWT_ENABLE') == True):
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

    api = eval('client.' + apiVersion + '(authClient)')
    
    return api