import argparse
import logging
import sys
import os

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from .customresources import *
#from .watcher import *

class watcherApplication():
    def __init__(self, apiInstance, crObject, operatorConfig):
        self.apiInstance = apiInstance

        #Unpack Object (See how to use self.crObject.customGroup)
        self.operatorConfig = operatorConfig
        self.customGroup = operatorConfig.customGroup
        self.customVersion = operatorConfig.customVersion
        self.customPlural = operatorConfig.customPlural
        self.customKind = operatorConfig.customKind

        self.watcherApplicationName = crObject['metadata']['name']
        self.deployNamespace = None
        self.watchNamespace = None
        self.k8sApiVersion = None
        self.k8sApiResourceName = None
        self.annotationFilterBoolean = None
        self.annotationFilterString = None
        self.eventTypeFilter = None
        self.fullJSONSpec = None
        self.status = None
        self.deleteTimestamp = None

        #Extract CR Object
        self.deployNamespace = crObject['spec']['deployNamespace']
        self.watchNamespace = crObject['spec']['watchNamespace']
        self.k8sApiVersion = crObject['spec']['k8sApiVersion']
        self.k8sApiResourceName = crObject['spec']['k8sApiResourceName']
        self.annotationFilterBoolean = crObject['spec']['annotationFilterBoolean']
        self.annotationFilterString = crObject['spec']['annotationFilterString']
        self.eventTypeFilter = crObject['spec']['eventTypeFilter']
        self.fullJSONSpec = crObject['spec']

    #not working yet.  have to figure out how to "inject" a status into existing body.
    #def update_status(self, newStatus):
        #currentConfig = get_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.watcherApplicationName)
        #Check by printing this.  
        #Overwrite the "status"
        #currentConfig.metadata.status = newStatus

        #Patch the actual resource.
        #api_response = patch_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.customKind, self.watcherApplicationName, currentConfig)
        #return api_response
    
    def check_marked_for_delete(self):
        try:
            currentConfig = get_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.watcherApplicationName)
            self.deleteTimestamp = currentConfig['metadata']['deletionTimestamp']
            return True
        except:
            self.deleteTimestamp = None
            return False
        
    def remove_finalizer(self):
        #Build Body to pass to customresources.patch
        noFinalizerBody = {
        "apiVersion": self.customGroup + '/' + self.customVersion,
        "kind": self.customKind,
        "metadata": {
            "name": self.watcherApplicationName,
            "finalizers": []
                    }
        }
        try:
            api_response = patch_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.customKind, self.watcherApplicationName, noFinalizerBody)
        except ApiException as e:
            logger.error("Finalizer Not removed. [Deployment: " + deploymentName + "] Error: %s\n" % e)

    
    def get_deployment_object(self):

        # Configureate Pod template container
        container = client.V1Container(
            name="watcher",
            image="image-registry.openshift-image-registry.svc:5000/watcher-operator/watcher-application:latest",
            ports=[client.V1ContainerPort(container_port=8080)],
            env=[client.V1EnvVar(name='ANNOTATION_FILTER_BOOLEAN',value=self.annotationFilterBoolean),
                client.V1EnvVar(name='ANNOTATION_FILTER_STRING',value=self.annotationFilterString),
                client.V1EnvVar(name='WATCH_NAMESPACE',value=self.watchNamespace),
                client.V1EnvVar(name='API_VERSION',value=self.k8sApiVersion),
                client.V1EnvVar(name='API_RESOURCE_NAME',value=self.k8sApiResourceName),
                client.V1EnvVar(name='PATH_TO_CA_PEM',value='/ca/route'),   #Figure out later.
                client.V1EnvVar(name='JWT_TOKEN',value='141819048109481094')    #Figure out later.
                ]
        )
        # Create and configurate a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": self.watcherApplicationName}),
            spec=client.V1PodSpec(service_account="watcher-application",
                                service_account_name="watcher-application",
                                containers=[container]))

# # Create and configurate a spec section
#         template = client.V1PodTemplateSpec(
#             metadata=client.V1ObjectMeta(labels={"app": self.watcherApplicationName}),
#             spec=client.V1PodSpec(containers=[container]))            
        # Create the specification of deployment
        spec = client.V1DeploymentSpec(
            replicas=1,
            template=template,
            selector={'matchLabels': {'app':  self.watcherApplicationName}})
        # Instantiate the deployment object
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name= self.watcherApplicationName),
            spec=spec)
        return deployment

    