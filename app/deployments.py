"""
Creates, updates, and deletes a deployment using AppsV1Api.
"""
import logging

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

class deployment():
    def __init__(self, deploymentName, image, serviceAccount=None, deployPorts=None):
        self.deploymentName = deploymentName
        self.deployImage = image
        self.serviceAccount = serviceAccount
        self.deployPorts = deployPorts

    def _fetch_deployment_definition(self, deploymentName, deployImage, deployPorts, serviceAccount):
        # Configureate Pod template container
            container = client.V1Container(
                name=self.deploymentName,
                image=self.deployImage,
                ports=[client.V1ContainerPort(container_port=self.deployPorts)]
            )
            # Create and configurate a spec section
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": self.deploymentName}),
                spec=client.V1PodSpec(service_account_name=self.serviceAccount,
                                    containers=[container]))

    # # Create and configurate a spec section
    #         template = client.V1PodTemplateSpec(
    #             metadata=client.V1ObjectMeta(labels={"app": self.watcherApplicationName}),
    #             spec=client.V1PodSpec(containers=[container]))            
            # Create the specification of deployment
            spec = client.V1DeploymentSpec(
                replicas=1,
                template=template,
                selector={'matchLabels': {'app': self.deploymentName}})
            # Instantiate the deployment object
            deployment = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(name= self.deploymentName),
                spec=spec)
            return deployment

def build_api_instance(authorizedClient):
    apiInstance = client.AppsV1Api(authorizedClient)
    return apiInstance

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
        logger.error("Deployment not deleted. [Deployment: " + deploymentName + "][DELETE] Error: %s\n" % e)


def check_for_deployment(apiInstance, deploymentName, deploymentNamespace):
    try:
        api_response = apiInstance.read_namespaced_deployment(name=deploymentName, namespace=deploymentNamespace)
        return True
    except ApiException as e:
        return False

def create_quick_deployment_definition(deploymentName, deployImage, deployPorts, serviceAccount):
    # Configureate Pod template container
        container = client.V1Container(
            name=deploymentName,
            image=deployImage,
            ports=[client.V1ContainerPort(container_port=deployPorts)]
        )
        # Create and configurate a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": deploymentName}),
            spec=client.V1PodSpec(service_account=serviceAccount,
                                service_account_name=serviceAccount,
                                containers=[container]))

# # Create and configurate a spec section
#         template = client.V1PodTemplateSpec(
#             metadata=client.V1ObjectMeta(labels={"app": self.watcherApplicationName}),
#             spec=client.V1PodSpec(containers=[container]))            
        # Create the specification of deployment
        spec = client.V1DeploymentSpec(
            replicas=1,
            template=template,
            selector={'matchLabels': {'app':  deploymentName}})
        # Instantiate the deployment object
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name= deploymentName),
            spec=spec)
        return deployment


