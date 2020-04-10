"""
Creates, updates, and deletes a deployment using AppsV1Api.
"""
import logging

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

def build_api_instance(authorizedClient):
    apiInstance = client.CoreV1Api(authorizedClient)
    return apiInstance

def create_quick_sa_definition(saName, saNamespace, annotationsDict={}):
    serviceaccount = client.V1ServiceAccount(
            api_version="v1",
            kind="ServiceAccount",
            metadata=client.V1ObjectMeta(name= saName, namespace=saNamespace, annotations=annotationsDict)
    )
    return serviceaccount


def create_serviceaccount(authorizedClient, saBody, saNamespace):

    try:
        apiInstance = build_api_instance(authorizedClient)
        api_response = apiInstance.create_namespaced_service_account(body=saBody, namespace=saNamespace)
    except ApiException as e:
        logger.error("ServiceAccount not created. [ServiceAccount] [CREATE] Error: %s\n" % e)
        logger.error("ServiceAccount YAML: " + str(saBody))

def update_serviceaccount(authorizedClient, saName, saNamespace, saBody):

    try:
        apiInstance = build_api_instance(authorizedClient)
        api_response = apiInstance.patch_namespaced_service_account(name=saName, namespace=saNamespace, body=saBody)
    except ApiException as e:
        logger.error("ServiceAccount not patched. [ServiceAccount: " + saName + "] [PATCH] Error: %s\n" % e)


def delete_serviceaccount(authorizedClient, saName, saNamespace):

    try:
        apiInstance = build_api_instance(authorizedClient)
        deleteBody = client.V1DeleteOptions() # V1DeleteOptions |  (optional)

        api_response = apiInstance.delete_cluster_role_binding(name=saName, body=deleteBody)
    except ApiException as e:
        logger.error("ServiceAccount not deleted. [ServiceAccount: " + saName + "] [DELETE] Error: %s\n" % e)

def check_for_serviceaccount(authorizedClient, saName, saNamespace):
    try:
        apiInstance = build_api_instance(authorizedClient)
        api_response = apiInstance.read_namespaced_service_account(name=saName, namespace=saNamespace)
        return True
    except ApiException as e:
        return False