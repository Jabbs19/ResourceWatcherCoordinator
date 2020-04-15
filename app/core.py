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


def create_serviceaccount(apiInstance, saBody, saNamespace):

    try:
        api_response = apiInstance.create_namespaced_service_account(body=saBody, namespace=saNamespace)
    except ApiException as e:
        logger.error("ServiceAccount not created. [ServiceAccount] [CREATE] Error: %s\n" % e)
        logger.error("ServiceAccount YAML: " + str(saBody))

def update_serviceaccount(apiInstance, saName, saNamespace, saBody):

    try:
        api_response = apiInstance.patch_namespaced_service_account(name=saName, namespace=saNamespace, body=saBody)
    except ApiException as e:
        logger.error("ServiceAccount not patched. [ServiceAccount: " + saName + "] [PATCH] Error: %s\n" % e)


def delete_serviceaccount(apiInstance, saName, saNamespace):

    try:
        deleteBody = client.V1DeleteOptions() # V1DeleteOptions |  (optional)

        api_response = apiInstance.delete_namespaced_service_account(name=saName, namespace=saNamespace, body=deleteBody)
    except ApiException as e:
        logger.error("ServiceAccount not deleted. [ServiceAccount: " + saName + "] [DELETE] Error: %s\n" % e)

def check_for_serviceaccount(apiInstance, saName, saNamespace):
    try:
        api_response = apiInstance.read_namespaced_service_account(name=saName, namespace=saNamespace)
        return True
    except ApiException as e:
        return False




def create_quick_configmap_definition(cmName, cmNamespace, annotationsDict={}):
    configmap = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            data={"__init__.py": "",
                "custompython.py": "import argparse\nimport logging\nimport sys\nimport os\n\nfrom kubernetes import client, config\nfrom kubernetes.client import rest\n\nlogger = logging.getLogger('custom')\nlogging.basicConfig(level=logging.INFO)\n\n\ndef test_custom_code(input=None):\n    if input==None:\n        logger.info(\"[Message: %s]\" % (\"Custom Code invoked!!!! (v2) \"))\n    else:\n        logger.info(\"[Message: %s]\" % (\"Custom Input (v2): \" + input))\n\n"
            },
            metadata=client.V1ObjectMeta(name= cmName, namespace=cmNamespace, annotations=annotationsDict)
    )
    return configmap


def create_configmap(apiInstance, cmBody, cmNamespace):

    try:
        api_response = apiInstance.create_namespaced_config_map(body=cmBody, namespace=cmNamespace)
    except ApiException as e:
        logger.error("ConfigMap not created. [ConfigMap] [CREATE] Error: %s\n" % e)
        logger.error("ConfigMap YAML: " + str(cmBody))

def update_configmap(apiInstance, cmName, cmNamespace, cmBody):

    try:
        api_response = apiInstance.patch_namespaced_config_map(name=cmName, namespace=cmNamespace, body=cmBody)
    except ApiException as e:
        logger.error("ConfigMap not patched. [ConfigMap: " + cmName + "] [PATCH] Error: %s\n" % e)


def delete_configmap(apiInstance, cmName, cmNamespace):

    try:
        deleteBody = client.V1DeleteOptions() # V1DeleteOptions |  (optional)

        api_response = apiInstance.delete_namespaced_config_map(name=cmName, namespace=cmNamespace, body=deleteBody)
    except ApiException as e:
        logger.error("ConfigMap not deleted. [ConfigMap: " + cmName + "] [DELETE] Error: %s\n" % e)

def check_for_configmap(apiInstance, cmName, cmNamespace):
    try:
        api_response = apiInstance.read_namespaced_config_map(name=cmName, namespace=cmNamespace)
        return True
    except ApiException as e:
        return False        