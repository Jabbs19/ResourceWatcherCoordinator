import logging
import queue
import threading
import json

from kubernetes.client.rest import ApiException
from kubernetes.client import models
from kubernetes import client, config
import copy

#k8s stuff
from .deployments import *
from .customresources import *
from .rbac import *
from .core import *
from .simpleclient import *


logger = logging.getLogger('coordinator')

#Coorindator (Operator) object
class coordinator():
    #def __init__(self, customGroup, customVersion, customPlural, customKind, apiVersion, customEventFilter, deployEventFilter):
    def __init__(self, authorizedClient):
        self.customGroup = "jabbs19.com"
        self.customVersion = "v1"
        self.customPlural = "resourcewatchers"
        self.customKind = "ResourceWatcher"

        self.customApiVersion = "CustomObjectsApi"
        self.customEventFilter =  {'eventTypesList': ['ADDED','MODIFIED','DELETED']}
        self.customApiInstance = client.CustomObjectsApi(authorizedClient)

        self.deploymentApiVersion = "AppsV1Api"
        self.deployEventFilter = {'eventTypesList': ['zz']}
        self.deploymentApiInstance = client.AppsV1Api(authorizedClient)

        self.finalizer = ['watcher.delete.finalizer']

        self.authorizedClient = authorizedClient

        self.coreAPI = client.CoreV1Api(authorizedClient)
        self.coreAPIfilter = {'eventTypesList': ['MODIFIED']}
        self.rbacAPI = client.RbacAuthorizationV1Api(authorizedClient) 
        self.rbacAPIfilter = {'eventTypesList': ['MODIFIED']}

        self.annotationFilterKey = "resourceWatcherParent"
        self.annotationFilterValue = "resource-watcher-service"   #Optional?
    

#
#Global Functions for Operators  
#
#  

def get_annotation_value(annotationFilterKey, annotationDict):

    try:
        annotationValue = annotationDict.get(annotationFilterKey, "")
    except:
        annotationValue = None
        
    if annotationValue:
        return annotationValue
    else:
        return None


def check_marked_for_delete(authorizedClient, object_key, customGroup, customVersion, customPlural):
    eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

    if eventObject == 'ResourceWatcher':
        operandName = objectName
        try:
            operandBody = get_custom_resource(authorizedClient, operandName, customGroup, customVersion, customPlural )
            if (operandBody['metadata']['deletionTimestamp'] != ""):
                return True
            else:
                return False

        except:
            return False
    else:
        return False
    




def load_configuration_object(authorizedClient, object_key, *args, **kwargs):
    try:
        eventType, eventObject, objectName, objectNamespace, annotation = object_key.split("~~")
        #watcherConfigExist = check_for_custom_resource(objectName, *self.func_args, **self.func_kwargs) self.customAPI, self.customGroup, self.customVersion, self.customPlural, objectName)
        
        #List the monitored objects that you want to use annotations to "trigger" events
        if eventObject in ['ServiceAccount','ClusterRole','ClusterRoleBinding']:
            lookupValue = annotation
        elif eventObject in ['Deployment','ResourceWatcher']:
            lookupValue = objectName

        try:
            rwOperand = get_custom_resource(authorizedClient, lookupValue, *args, **kwargs) 
        except:
            rwOperand = None

        if rwOperand:
            return rwOperand, True
        else:
            return None, False

    except ApiException as e:
        logger.info("No Object Found for 'should event be processed': {:s}".format(object_key))
        logger.error("Error:" + e)
        return None, False




class resourceWatcher():
    def __init__(self, crOperand, crdObject):

        #Unpack Object (See how to use self.crObject.customGroup)
        self.crdObject = crdObject
        self.customGroup = crdObject.customGroup
        self.customVersion = crdObject.customVersion
        self.customPlural = crdObject.customPlural
        self.customKind = crdObject.customKind

        self.resourceWatcherName = crOperand['metadata']['name']
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
        self.deployNamespace = crOperand['spec']['deployNamespace']
        self.watchNamespace = crOperand['spec']['watchNamespace']
        self.k8sApiVersion = crOperand['spec']['k8sApiVersion']
        self.k8sApiResourceName = crOperand['spec']['k8sApiResourceName']
        self.annotationFilterBoolean = crOperand['spec']['annotationFilterBoolean']
        self.annotationFilterString = crOperand['spec']['annotationFilterString']
        self.eventTypeFilter = crOperand['spec']['eventTypeFilter']
        self.fullJSONSpec = crOperand['spec']
        #Need to add these to CR or hardcode
        self.serviceAccountName = self.resourceWatcherName + '-sa'
        self.clusterRoleName = self.resourceWatcherName + '-clusterrole'
        self.clusterRoleBindingName = self.resourceWatcherName + '-clusterrolebinding'
        #Annotation Creation
        try:
            # annotationString = {}
            #     self.crdObject.annotationFilterKey
            # }
            # annotationDict = json.loads(self.crdObject.annotationFilterKey+":"+self.resourceWatcherName) 
            annotationDict = {self.crdObject.annotationFilterKey:self.resourceWatcherName}
        except:
            annotationDict = None
            print('annotation creation did not work')
        self.annotationStringForCreation = annotationDict

    def process_marked_for_deletion(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

        delete_deployment(self.crdObject.authorizedClient, objectName, objectNamespace)
        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                    "Deployment Deleted")) 

        delete_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName)
        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                    "ClusterRoleBinding Deleted")) 

        delete_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName)
        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                    "ClusterRole Deleted")) 

        delete_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, objectNamespace)
        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
            "ServiceAccount Deleted")) 

        self.remove_finalizer()

    
    def process_modified_event(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

        if eventObject == 'ServiceAccount':
            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace, self.annotationStringForCreation)
            if check_for_serviceaccount(self.crdObject.authorizedClient,self.serviceAccountName,self.deployNamespace) == True:
                update_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, self.deployNamespace, saBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Service Account Updated")) 
            else:
                create_serviceaccount(self.crdObject.authorizedClient,saBody,self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Service Account Created")) 

        if eventObject == 'ClusterRole':
            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet', self.annotationStringForCreation)
            if check_for_clusterrole(self.crdObject.authorizedClient,self.clusterRoleName) == True:
                update_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName, clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 
                                        
            else:
                create_clusterrole(self.crdObject.authorizedClient,clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 
                            
        if eventObject == 'ClusterRoleBinding':
            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace, self.annotationStringForCreation)
            if check_for_clusterrolebinding(self.crdObject.authorizedClient,self.clusterRoleBindingName) == True:
                update_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName,     crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 
            else:
                create_clusterrolebinding(self.crdObject.authorizedClient,crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 
                                            

        if eventObject == 'Deployment':
            deployBody = self._build_deployment_definition()
            if check_for_deployment(self.crdObject.authorizedClient,self.resourceWatcherName, self.deployNamespace) == True:
                update_deployment(self.crdObject.authorizedClient, deployBody, objectName, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 
                                            
            else:
                create_deployment(self.crdObject.authorizedClient, deployBody, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 
                                            

        if eventObject == 'ResourceWatcher':
            #Deploy All
            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace, self.annotationStringForCreation)
            if check_for_serviceaccount(self.crdObject.authorizedClient,self.serviceAccountName,self.deployNamespace) == True:
                update_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, objectNamespace, saBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ResourceWatcher Updated")) 
                                            
            else:
                create_serviceaccount(self.crdObject.authorizedClient,saBody,self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ResourceWatcher Updated")) 

            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet', self.annotationStringForCreation)
            if check_for_clusterrole(self.crdObject.authorizedClient,self.clusterRoleName) == True:
                update_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName, clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 
                                        
            else:
                create_clusterrole(self.crdObject.authorizedClient,clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 

            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace, self.annotationStringForCreation)
            if check_for_clusterrolebinding(self.crdObject.authorizedClient,self.clusterRoleBindingName) == True:
                update_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName,     crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 
            else:
                create_clusterrolebinding(self.crdObject.authorizedClient,crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 

            deployBody = self._build_deployment_definition()
            if check_for_deployment(self.crdObject.authorizedClient,self.resourceWatcherName, self.deployNamespace) == True:
                update_deployment(self.crdObject.authorizedClient, deployBody, objectName, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 
                                            
            else:
                create_deployment(self.crdObject.authorizedClient, deployBody, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 

 
       
    def process_added_event(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")


        if eventObject == 'ResourceWatcher':
            #Deploy All
            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace, self.annotationStringForCreation)
            if check_for_serviceaccount(self.crdObject.authorizedClient,self.serviceAccountName,self.deployNamespace) == True:
                update_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, objectNamespace, saBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ResourceWatcher Updated")) 
                                            
            else:
                create_serviceaccount(self.crdObject.authorizedClient,saBody,self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ResourceWatcher Updated")) 

            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet', self.annotationStringForCreation)
            if check_for_clusterrole(self.crdObject.authorizedClient,self.clusterRoleName) == True:
                update_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName, clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 
                                        
            else:
                create_clusterrole(self.crdObject.authorizedClient,clusterroleBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRole Updated")) 

            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace, self.annotationStringForCreation)
            if check_for_clusterrolebinding(self.crdObject.authorizedClient,self.clusterRoleBindingName) == True:
                update_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName,     crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 
            else:
                create_clusterrolebinding(self.crdObject.authorizedClient,crBindingBody)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "ClusterRoleBinding Updated")) 

            deployBody = self._build_deployment_definition()
            if check_for_deployment(self.crdObject.authorizedClient,self.resourceWatcherName, self.deployNamespace) == True:
                update_deployment(self.crdObject.authorizedClient, deployBody, objectName, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 
                                            
            else:
                create_deployment(self.crdObject.authorizedClient, deployBody, self.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, objectName, objectNamespace, 
                            "Deployment Updated")) 

        
    def remove_finalizer(self):
        #Build Body to pass to customresources.patch
        noFinalizerBody = {
        "apiVersion": self.crdObject.customGroup + '/' + self.crdObject.customVersion,
        "kind": self.crdObject.customKind,
        "metadata": {
            "name": self.resourceWatcherName,
            "finalizers": []
                    }
        }
        try:
            print("noFinalizerBody:" + str(noFinalizerBody))
            api_response = patch_custom_resource(self.crdObject.authorizedClient, self.crdObject.customGroup, self.crdObject.customVersion, self.crdObject.customPlural, self.resourceWatcherName, noFinalizerBody)
        except ApiException as e:
            logger.error("Finalizer Not removed. [ResourceWatcherName: " + self.resourceWatcherName + "] Error: %s\n" % e)

    
    def _build_deployment_definition(self):

        # Configureate Pod template container
        container = client.V1Container(
            name="resource-watcher",
           # image="image-registry.openshift-image-registry.svc:5000/watcher-operator/watcher-application:latest",
            image="busybox",
            command= ["/bin/sh", "-c", "tail -f /dev/null"],
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
            metadata=client.V1ObjectMeta(labels={"app": self.resourceWatcherName}),
            spec=client.V1PodSpec(service_account=self.serviceAccountName,
                                service_account_name=self.serviceAccountName,
                                containers=[container]))

# # Create and configurate a spec section
#         template = client.V1PodTemplateSpec(
#             metadata=client.V1ObjectMeta(labels={"app": self.watcherApplicresourceWatcherNameationName}),
#             spec=client.V1PodSpec(containers=[container]))            
        # Create the specification of deployment
        spec = client.V1DeploymentSpec(
            replicas=1,
            template=template,
            selector={'matchLabels': {'app':  self.resourceWatcherName}})
        # Instantiate the deployment object
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name= self.resourceWatcherName,annotations=self.annotationStringForCreation),
            spec=spec)
        return deployment

def process_deleted_event(object_key, *args, **kwargs):
    eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                    "Object Delete.")) 
                #Since only sending "delete" events for custom resource, this is truly once its been deleted. 
                #Can't use for deleting deployment.
    #             #watcherApplicationConfig.updateStatus(objectName, 'Deleted')   
     

   
