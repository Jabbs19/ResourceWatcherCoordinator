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
logging.basicConfig(level=logging.INFO)

class crd():
    def __init__(self, customGroup, customVersion, customPlural, customKind):
        self.customGroup = customGroup
        self.customVersion = customVersion
        self.customPlural = customPlural
        self.customKind = customKind

class eventObject():
    def __init__(self, event):
        #Don't need to carry this whole object through, could just parse what's needed to make it slimmer.
        self.fullEventObject = event
        self.annotationFilterValue = None
        try:
            self.eventType = event['type']
            self.eventObjectType = event['object']['kind']
        except:
            self.eventType = self.fullEventObject['type']                                           #ADDED, MODIFIED, etc.
            self.eventObjectType = self.fullEventObject['object'].kind                         #ServiceAccount, Deployment, Pod

        if self.eventObjectType == 'ResourceWatcher':
            self._process_custom_event(event)
        else:
            self._process_standard_event(event)

    def _process_custom_event(self, event):

        self.objectName = event['object']['metadata']['name']
        self.objectNamespace = event['object']['spec']['deployNamespace']
        self.annotationFilterValue = 'NONE'

        self.eventKey = self.eventType + "~~" + self.eventObjectType + "~~" + self.objectName + "~~" + self.objectNamespace
       # self._queue_work(name)

    def _process_standard_event(self, event):
     
        try:
            self.objectName = self.fullEventObject['object'].metadata.name                      #Deployment Name, Pod Name, etc.
        except:
            self.objectName = self.fullEventObject['object']['metadata']['name']

        try:
            self.objectNamespace = self.fullEventObject['object'].metadata.namespace
        except:
            self.objectNamespace = self.fullEventObject['object']['metadata']['namespace']
        if self.objectNamespace == None:
            self.objectNamespace = 'GLOBAL'            
       
        #Deprecated object key for parsing, but can just use direct ref now.   
        self.eventKey = self.eventType + "~~" + self.eventObjectType + "~~" + self.objectName + "~~" + self.objectNamespace

        #Other
        self.annotationFilterValue = None

#Coorindator (Operator) object
class coordinator():
    #def __init__(self, customGroup, customVersion, customPlural, customKind, apiVersion, customEventFilter, deployEventFilter):
    def __init__(self, authorizedClient):
        self.authorizedClient = authorizedClient
        
        #Running Operator (Controller) Values.  FIXED.
        self.customApiVersion = "CustomObjectsApi"
        self.customEventFilter =  ['ADDED','MODIFIED','DELETED']
        self.customApiInstance = client.CustomObjectsApi(authorizedClient)

        self.deploymentApiVersion = "AppsV1Api"
        self.deployEventFilter = ['MODIFIED']
        self.deploymentApiInstance = client.AppsV1Api(authorizedClient)

        self.coreAPI = client.CoreV1Api(authorizedClient)
        self.coreAPIfilter = ['MODIFIED']
        self.rbacAPI = client.RbacAuthorizationV1Api(authorizedClient) 
        self.rbacAPIfilter = ['MODIFIED']

        self.childAnnotationFilterKey = "resource-watcher-application-name"
    
        #Maybe not needed
        self.finalizer = ['watcher.delete.finalizer']


class resourceWatcher():
    def __init__(self, crOperand, parentAnnotationFilterKey):

        self.resourceWatcherName = crOperand['metadata']['name']
        self.deployNamespace = crOperand['spec']['deployNamespace']
        self.watchNamespace = crOperand['spec']['watchNamespace']
        self.k8sApiVersion = crOperand['spec']['k8sApiVersion']
        self.k8sApiResourceName = crOperand['spec']['k8sApiResourceName']
        self.annotationFilterKey = crOperand['spec']['annotationFilterKey']


        # tempString = crOperand['spec']['eventTypeFilterString']
        # asArray = eval(tempString)
        self.eventTypeFilter = crOperand['spec']['eventTypeFilter']     #Deprecated in favor of straight string, which is eval'd in applicatin.
        self.eventTypeFilterString = crOperand['spec']['eventTypeFilterString']


        ####ADD to CRD and Operand
        self.k8sAPIkwArgs = crOperand['spec']['k8sAPIkwArgs']    #'{"namespace":"resource-watcher-testnamespace"}'
        self.eventAction = crOperand['spec']['eventAction'] 
        self.pathToCa = crOperand['spec']['pathToCa'] 
        self.jwtTokenValue = crOperand['spec']['jwtTokenValue'] 

        #Leave as "auto" or move to CRD?
        self.serviceAccountName = self.resourceWatcherName + '-sa'
        self.clusterRoleName = self.resourceWatcherName + '-clusterrole'
        self.clusterRoleBindingName = self.resourceWatcherName + '-clusterrolebinding'
        self.configMapName =  self.resourceWatcherName + '-custom-code'

    #Auto Generate
        self.parentAnnotationFilterKey = parentAnnotationFilterKey
        self.annotationFilterFinalDict = {self.parentAnnotationFilterKey:self.resourceWatcherName}


    def _build_deployment_definition(self):

        customCodeVolume = client.V1Volume(
            name=self.configMapName,
            config_map=client.V1ConfigMapVolumeSource(
                name=self.configMapName
            )
        )
        # Configureate Pod template container
        container = client.V1Container(
            name="resource-watcher",
           # image="image-registry.openshift-image-registry.svc:5000/watcher-operator/watcher-application:latest",
            image="image-registry.openshift-image-registry.svc:5000/resource-watcher-coordinator/resource-watcher-application:latest",
            # command= ["/bin/sh", "-c", "tail -f /dev/null"],
            ports=[client.V1ContainerPort(container_port=8080)],
            env=[client.V1EnvVar(name='RESOURCE_WATCHER_NAME',value=self.resourceWatcherName),
                client.V1EnvVar(name='DEPLOY_NAMESPACE',value=self.deployNamespace),
                client.V1EnvVar(name='WATCH_NAMESPACE',value=self.watchNamespace),
                client.V1EnvVar(name='K8S_API_VERSION',value=self.k8sApiVersion),
                client.V1EnvVar(name='K8S_API_RESOURCE',value=self.k8sApiResourceName),

                client.V1EnvVar(name='K8S_ADDITIONAL_KWARGS',value=self.k8sAPIkwArgs),

                client.V1EnvVar(name='ANNOTATION_FILTER_KEY',value=self.annotationFilterKey),
                client.V1EnvVar(name='EVENT_TYPE_FILTER',value=self.eventTypeFilterString),
                client.V1EnvVar(name='PARENT_OPERATOR_ANNOTATION_FILTER_KEY',value=self.parentAnnotationFilterKey),
                client.V1EnvVar(name='EVENT_ACTION',value=self.eventAction),

                client.V1EnvVar(name='PATH_TO_CA',value=self.pathToCa),   #Figure out later.
                client.V1EnvVar(name='JWT_TOKEN',value=self.jwtTokenValue)    #Figure out later.
                ],
            volume_mounts=[client.V1VolumeMount(
                name=self.configMapName,
                mount_path= "/customcode"
                )]
        )
        # Create and configurate a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": self.resourceWatcherName}),
            spec=client.V1PodSpec(service_account=self.serviceAccountName,
                                service_account_name=self.serviceAccountName,
                                containers=[container],
                                volumes=[customCodeVolume]

                                )
                    )

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
            metadata=client.V1ObjectMeta(name= self.resourceWatcherName,annotations=self.annotationFilterFinalDict),
            spec=spec)
        return deployment

def should_event_be_processed(eventObject, crdObject, rwCoordinatorObject, *args, **kwargs):
    try:
        #List the monitored objects that you want to use annotations to "trigger" events
        if eventObject.eventObjectType in ['ServiceAccount','ClusterRole','ClusterRoleBinding']:
           
            try:
                #annotationsDict = eventObject['object'].metadata.annotations
                annotationsDict = eventObject.fullEventObject['object'].metadata.annotations

            except:
                annotationsDict = eventObject.fullEventObject['object']['metadata']['annotations']

            if annotationsDict == None:
                return False
            else:
                try:
                    lookupValue = eventObject.annotationDict.get(rwCoordinatorObject.childAnnotationFilterKey, "")
                except:
                    return False
                    
        elif eventObject.eventObjectType in ['Deployment','ResourceWatcher']:
            lookupValue = eventObject.objectName
   
        try:
            rwOperand = check_for_custom_resource(rwCoordinatorObject.customApiInstance, lookupValue, crdObject.customGroup,crdObject.customVersion, crdObject.customPlural)
        except:
            return False

        if rwOperand:
            return True
        else:
            return False

    except ApiException as e:
        logger.info("No Object Found for 'should event be processed': {:s}".format(lookupValue))
        logger.error("Error:" + e)
        return False


def load_configuration_operand(eventObject, crdObject, rwCoordinatorObject, *args, **kwargs):
    try:
        #List the monitored objects that you want to use annotations to "trigger" events
        if eventObject.eventObjectType in ['ServiceAccount','ClusterRole','ClusterRoleBinding']:
           
            try:
                #annotationsDict = eventObject['object'].metadata.annotations
                annotationsDict = eventObject.fullEventObject['object'].metadata.annotations

            except:
                annotationsDict = eventObject.fullEventObject['object']['metadata']['annotations']

            if annotationsDict == None:
                return None
            else:
                try:
                    lookupValue = eventObject.annotationDict.get(rwCoordinatorObject.childAnnotationFilterKey, "")
                except:
                    return None
                    
        elif eventObject.eventObjectType in ['Deployment','ResourceWatcher']:
            lookupValue = eventObject.objectName

   
        try:
            rwOperand = get_custom_resource(rwCoordinatorObject.customApiInstance, lookupValue, crdObject.customGroup,crdObject.customVersion, crdObject.customPlural)
        except:
            return None

        return rwOperand

    except ApiException as e:
        logger.info("No Object Found for 'should event be processed': {:s}".format(lookupValue))
        logger.error("Error:" + e)
        return None


def process_deleted_event(eventObject, *args, **kwargs):
    logger.info("[Message: %s] [Object: %s]" % ("DELETED Event Processed", str(eventObject.objectName)))
    

def check_marked_for_delete(eventObject, crdObject, rwCoordinatorObject, *args, **kwargs):

    if eventObject.eventObjectType == 'ResourceWatcher':
        operandName = eventObject.objectName
        try:
            operandBody = get_custom_resource(rwCoordinatorObject.customApiInstance, operandName, crdObject.customGroup,crdObject.customVersion, crdObject.customPlural)
            if (operandBody['metadata']['deletionTimestamp'] != ""):
                return True
            else:
                return False

        except:
            return False
    else:
        return False

def process_marked_for_deletion(eventObject, crdObject, rwCoordinatorObject, rwObject, *args, **kwargs):

    if check_for_deployment(rwCoordinatorObject.deploymentApiInstance,rwObject.resourceWatcherName, rwObject.deployNamespace) == True:
        delete_deployment(rwCoordinatorObject.deploymentApiInstance, rwObject.resourceWatcherName, rwObject.deployNamespace)
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                "Deployment Deleted")) 
    
    if check_for_clusterrolebinding(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleBindingName) == True:
        delete_clusterrolebinding(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleBindingName)
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                "ClusterRoleBinding Deleted")) 

    if check_for_clusterrole(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleName) == True:
        delete_clusterrole(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleName)
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                "ClusterRole Deleted")) 
    
    if check_for_serviceaccount(rwCoordinatorObject.coreAPI,rwObject.serviceAccountName,rwObject.deployNamespace) == True:
        delete_serviceaccount(rwCoordinatorObject.coreAPI, rwObject.serviceAccountName, rwObject.deployNamespace)
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                "ServiceAccount Deleted")) 
    
    if check_for_configmap(rwCoordinatorObject.coreAPI,rwObject.configMapName, rwObject.deployNamespace) == True:
        delete_configmap(rwCoordinatorObject.coreAPI, rwObject.configMapName, rwObject.deployNamespace)
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                "ConfigMap Deleted")) 

    remove_finalizer(crdObject, rwCoordinatorObject, eventObject.objectName)
    
def remove_finalizer(crdObject, rwCoordinatorObject, rwName):

    #Build Body to pass to customresources.patch
    noFinalizerBody = {
    "apiVersion": crdObject.customGroup + '/' + crdObject.customVersion,
    "kind": crdObject.customKind,
    "metadata": {
        "name": rwName,
        "finalizers": []
                }
    }
    try:
        # print("noFinalizerBody:" + str(noFinalizerBody))
        api_response = patch_custom_resource(rwCoordinatorObject.customApiInstance, crdObject.customGroup, crdObject.customVersion, crdObject.customPlural, rwName, noFinalizerBody)
    except ApiException as e:
        logger.error("Finalizer Not removed. [ResourceWatcherName: " + rwName + "] Error: %s\n" % e)


def process_added_event(eventObject, crdObject, rwCoordinatorObject, rwObject, *args, **kwargs):


    if eventObject.eventObjectType == 'ResourceWatcher':
    #Deploy All
        #Onetime deploy of this?  This allows others to use it from here.
        
        cmBody = create_quick_configmap_definition(rwObject.configMapName, rwObject.deployNamespace,rwObject.annotationFilterFinalDict)
        if check_for_configmap(rwCoordinatorObject.coreAPI,rwObject.configMapName, rwObject.deployNamespace) == True:
            #create_config_map(rwCoordinatorObject.coreAPI,cmBody,rwObject.deployNamespace)
           # update_configmap(rwCoordinatorObject.coreAPI, rwObject.configMapName, rwObject.deployNamespace, cmBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ConfigMap Already Exists")) 
        else:
            create_configmap(rwCoordinatorObject.coreAPI,cmBody,rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ConfigMap Created"))       

        saBody = create_quick_sa_definition(rwObject.serviceAccountName, rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_serviceaccount(rwCoordinatorObject.coreAPI,rwObject.serviceAccountName,rwObject.deployNamespace) == True:
            update_serviceaccount(rwCoordinatorObject.coreAPI, rwObject.serviceAccountName,rwObject.deployNamespace, saBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Updated")) 
        else:
            create_serviceaccount(rwCoordinatorObject.coreAPI,saBody,rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Created")) 

        clusterroleBody = create_quick_clusterrole_definition(rwObject.clusterRoleName, 'rules not implemented yet', rwObject.annotationFilterFinalDict)
        if check_for_clusterrole(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleName) == True:
            update_clusterrole(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleName, clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                                    
        else:
            create_clusterrole(rwCoordinatorObject.rbacAPI,clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                        
        crBindingBody = create_quick_clusterrolebinding_definition(rwObject.clusterRoleBindingName,rwObject.clusterRoleName,rwObject.serviceAccountName,rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_clusterrolebinding(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleBindingName) == True:
            update_clusterrolebinding(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleBindingName,     crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
        else:
            create_clusterrolebinding(rwCoordinatorObject.rbacAPI,crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
                                        

        deployBody = rwObject._build_deployment_definition()
        if check_for_deployment(rwCoordinatorObject.deploymentApiInstance,rwObject.resourceWatcherName, rwObject.deployNamespace) == True:
            update_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody, eventObject.objectName, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 
                                        
        else:
            create_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 


    
def process_modified_event(eventObject, crdObject, rwCoordinatorObject, rwObject, *args, **kwargs):

    if eventObject.eventObjectType == 'ServiceAccount':
        saBody = create_quick_sa_definition(rwObject.serviceAccountName, rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_serviceaccount(rwCoordinatorObject.coreAPI,rwObject.serviceAccountName,rwObject.deployNamespace) == True:
            update_serviceaccount(rwCoordinatorObject.coreAPI, rwObject.serviceAccountName,rwObject.deployNamespace, saBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Updated")) 
        else:
            create_serviceaccount(rwCoordinatorObject.coreAPI,saBody,rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Created")) 

    if eventObject.eventObjectType == 'ClusterRole':
        clusterroleBody = create_quick_clusterrole_definition(rwObject.clusterRoleName, 'rules not implemented yet', rwObject.annotationFilterFinalDict)
        if check_for_clusterrole(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleName) == True:
            update_clusterrole(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleName, clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                                    
        else:
            create_clusterrole(rwCoordinatorObject.rbacAPI,clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                        
    if eventObject.eventObjectType == 'ClusterRoleBinding':
        crBindingBody = create_quick_clusterrolebinding_definition(rwObject.clusterRoleBindingName,rwObject.clusterRoleName,rwObject.serviceAccountName,rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_clusterrolebinding(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleBindingName) == True:
            update_clusterrolebinding(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleBindingName,     crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
        else:
            create_clusterrolebinding(rwCoordinatorObject.rbacAPI,crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
                                        

    if eventObject.eventObjectType == 'Deployment':
        deployBody = rwObject._build_deployment_definition()
        if check_for_deployment(rwCoordinatorObject.deploymentApiInstance,rwObject.resourceWatcherName, rwObject.deployNamespace) == True:
            update_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody, eventObject.objectName, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 
                                        
        else:
            create_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 
                                        

    if eventObject.eventObjectType == 'ResourceWatcher':
        #Deploy All
        saBody = create_quick_sa_definition(rwObject.serviceAccountName, rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_serviceaccount(rwCoordinatorObject.coreAPI,rwObject.serviceAccountName,rwObject.deployNamespace) == True:
            update_serviceaccount(rwCoordinatorObject.coreAPI, rwObject.serviceAccountName,rwObject.deployNamespace, saBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Updated")) 
        else:
            create_serviceaccount(rwCoordinatorObject.coreAPI,saBody,rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Service Account Created")) 

        clusterroleBody = create_quick_clusterrole_definition(rwObject.clusterRoleName, 'rules not implemented yet', rwObject.annotationFilterFinalDict)
        if check_for_clusterrole(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleName) == True:
            update_clusterrole(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleName, clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                                    
        else:
            create_clusterrole(rwCoordinatorObject.rbacAPI,clusterroleBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRole Updated")) 
                        
        crBindingBody = create_quick_clusterrolebinding_definition(rwObject.clusterRoleBindingName,rwObject.clusterRoleName,rwObject.serviceAccountName,rwObject.deployNamespace, rwObject.annotationFilterFinalDict)
        if check_for_clusterrolebinding(rwCoordinatorObject.rbacAPI,rwObject.clusterRoleBindingName) == True:
            update_clusterrolebinding(rwCoordinatorObject.rbacAPI, rwObject.clusterRoleBindingName,     crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
        else:
            create_clusterrolebinding(rwCoordinatorObject.rbacAPI,crBindingBody)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "ClusterRoleBinding Updated")) 
                                        

        deployBody = rwObject._build_deployment_definition()
        if check_for_deployment(rwCoordinatorObject.deploymentApiInstance,rwObject.resourceWatcherName, rwObject.deployNamespace) == True:
            update_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody,  eventObject.objectName, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 
                                        
        else:
            create_deployment(rwCoordinatorObject.deploymentApiInstance, deployBody, rwObject.deployNamespace)
            logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                        "Deployment Updated")) 

    


    


