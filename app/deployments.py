"""
Creates, updates, and deletes a deployment using AppsV1Api.
"""
import logging

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

def create_deployment(apiInstance, deploymentBody, deploymentNamespace):
    # Create deployement
    try:
        api_response = apiInstance.create_namespaced_deployment(body=deploymentBody,namespace=deploymentNamespace)
        logger.info("Deployment Created [" + api_response.metadata.name +"]")
    except ApiException as e:
        logger.error("Deployment not created. [Deployment: " + api_response.metadata.name + "][CREATE] Error: %s\n" % e)


def update_deployment(apiInstance, deploymentBody, deploymentName, deploymentNamespace):
    # Patch the deployment
    try:
        api_response = apiInstance.patch_namespaced_deployment(name=deploymentName,namespace=deploymentNamespace,body=deploymentBody)
        logger.info("Deployment Patched [" + deploymentName +"]")
    except ApiException as e:
        logger.error("Deployment not patched. [Deployment: " + deploymentName + "][PATCH] Error: %s\n" % e)


def delete_deployment(apiInstance, deploymentName, deploymentNamespace):
    # Delete deployment
    try:
        api_response = apiInstance.delete_namespaced_deployment(name=deploymentName, namespace=deploymentNamespace, body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=5))
        logger.info("Deployment Deleted [" + deploymentName +"]")
    except ApiException as e:
        logger.error("Deployment not patched. [Deployment: " + deploymentName + "][DELETE] Error: %s\n" % e)


def check_for_deployment(apiInstance, deploymentName, deploymentNamespace):
    try:
        api_response = apiInstance.read_namespaced_deployment(name=deploymentName, namespace=deploymentNamespace)
        return True
    except ApiException as e:
        return False

