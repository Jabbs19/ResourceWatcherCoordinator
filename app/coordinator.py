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

        self.deploymentApiVersion = "AppsV1Api"
        self.deployEventFilter = {'eventTypesList': ['MODIFIED']}

        self.finalizer = ['watcher.delete.finalizer']

        self.authorizedClient = authorizedClient

        self.coreAPI = client.CoreV1Api(authorizedClient)
        self.coreAPIfilter = {'eventTypesList': ['MODIFIED']}
        self.rbacAPI = client.RbacAuthorizationV1Api(authorizedClient) 
        self.rbacAPIfilter = {'eventTypesList': ['MODIFIED']}

        self.annotationFilterKey = "resourceWatcherParent"
        self.annotationFilterValue = "resource-watcher-service"   #Optional?
    
    def set_api_instance(self, customApiInstance, deploymentApiInstance):
        self.customApiInstance = customApiInstance
        self.deploymentApiInstance = deploymentApiInstance
    
    def autobuild_api_instances(self):
        self.customApiInstance = create_api_client(self.customApiVersion,self.authorizedClient)
        self.deploymentApiInstance = create_api_client(self.deploymentApiVersion,self.authorizedClient)
    


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


def check_marked_for_delete(authorizedClient, operandName, customGroup, customVersion, customPlural):
    try:
        operandBody = get_custom_resource(authorizedClient, operandName, customGroup, customVersion, customPlural )
        if (operandBody['metadata']['deletionTimestamp'] != ""):
            return True
        else:
            return False
    except:
        return False



def should_event_be_processed(authorizedClient, object_key, *args, **kwargs):
    try:
        eventType, eventObject, objectName, objectNamespace, annotation = object_key.split("~~")
        #watcherConfigExist = check_for_custom_resource(objectName, *self.func_args, **self.func_kwargs) self.customAPI, self.customGroup, self.customVersion, self.customPlural, objectName)
        
        #List the monitored objects that you want to use annotations to "trigger" events
        if eventObject in ['ServiceAccount','ClusterRole','ClusterRoleBinding']:
            lookupValue = annotation
        else:
            lookupValue = objectName

        resourceWatcherExist = check_for_custom_resource(authorizedClient, lookupValue, *args, **kwargs) 

        if resourceWatcherExist == True:
            return True
        else:
            return False
    except ApiException as e:
        logger.info("No Object Found for 'should event be processed': {:s}".format(object_key))
        logger.error("Error:" + e)
        return False
  
    
def load_config_object(authorizedClient, objectName, *args, **kwargs):
    # cr = get_custom_resource(objectName, self.customAPI, self.customGroup, self.customVersion, self.customPlural)
    cr = get_custom_resource(authorizedClient, objectName, *args, **kwargs) 
    return cr

    


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
            annotationDict = json.loads(self.crdObject.annotationFilterKey+":"+self.resourceWatcherName) 
        except:
            annotationDict = None
            print('annotation creation did not work')
        self.annotationStringForCreation = annotationDict

    def process_marked_for_deletion(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, additionalVars = object_key.split("~~")

        delete_deployment(self.crdObject.authorizedClient, objectName, objectNamespace)

        delete_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName)

        delete_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName)

        delete_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, objectNamespace)
        self.remove_finalizer()

    
    def process_modified_event(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, additionalVars = object_key.split("~~")

        # if check_for_deployment(args.deployAPI, objectName, objectNamespace):
        if check_for_deployment(self.crdObject.authorizedClient,objectName,objectNamespace):

            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace, self.annotationStringForCreation)
            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet', self.annotationStringForCreation)
            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace, self.annotationStringForCreation)
            deployBody = self._build_deployment_definition()

            #Could filter by event Object (Deployment, SA, Clusterrole, etc.), or could just redeploy whole solution when modified is found.
            update_serviceaccount(self.crdObject.authorizedClient, self.serviceAccountName, objectNamespace, saBody)
            update_clusterrole(self.crdObject.authorizedClient, self.clusterRoleName, clusterroleBody)
            update_clusterrolebinding(self.crdObject.authorizedClient, self.clusterRoleBindingName,     crBindingBody)
            update_deployment(self.crdObject.authorizedClient, deployBody, objectName, objectNamespace)

 

            #watcherApplicationConfig.updateStatus(deployOrConfigName, 'Added')

        else:
            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace, self.annotationStringForCreation)
            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet', self.annotationStringForCreation)
            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace, self.annotationStringForCreation)
            deployBody = self._build_deployment_definition()

            create_serviceaccount(self.crdObject.authorizedClient,saBody,self.deployNamespace)
            create_clusterrole(self.crdObject.authorizedClient,clusterroleBody)
            create_clusterrolebinding(self.crdObject.authorizedClient,crBindingBody)
            create_deployment(self.crdObject.authorizedClient, deployBody, self.deployNamespace)

   #               if check_for_deployment(self.deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace):
        #                   dep = watcherApplicationConfig.get_deployment_object()
        #                   update_deployment(self.deployAPI, dep, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace)
        #                   #watcherApplicationConfig.updateStatus(objectName, 'Added and Modified')

        #               else:
        #                   dep = watcherApplicationConfig.get_deployment_object()
        #                   create_deployment(self.deployAPI, dep, watcherApplicationConfig.deployNamespace)

    def process_deleted_event(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, additionalVars = object_key.split("~~")


                    #Since only sending "delete" events for custom resource, this is truly once its been deleted. 
                    #Can't use for deleting deployment.
      #             #watcherApplicationConfig.updateStatus(objectName, 'Deleted')    
       
       
    def process_added_event(self, object_key, *args, **kwargs):
        eventType, eventObject, objectName, objectNamespace, additionalVars = object_key.split("~~")

        # if check_for_deployment(args.deployAPI, objectName, objectNamespace):
        if check_for_deployment(self.crdObject.authorizedClient,objectName,objectNamespace):

            deployBody = self._build_deployment_definition()
            update_deployment(self.crdObject.authorizedClient, deployBody, objectName, objectNamespace)
            #watcherApplicationConfig.updateStatus(deployOrConfigName, 'Added')

        else:
            saBody = create_quick_sa_definition(self.serviceAccountName, self.deployNamespace)
            clusterroleBody = create_quick_clusterrole_definition(self.clusterRoleName, 'rules not implemented yet')
            crBindingBody = create_quick_clusterrolebinding_definition(self.clusterRoleBindingName,self.clusterRoleName,self.serviceAccountName,self.deployNamespace)
            deployBody = self._build_deployment_definition()

            create_serviceaccount(self.crdObject.authorizedClient,saBody,self.deployNamespace)
            create_clusterrole(self.crdObject.authorizedClient,clusterroleBody)
            create_clusterrolebinding(self.crdObject.authorizedClient,crBindingBody)
            create_deployment(self.crdObject.authorizedClient, deployBody, self.deployNamespace)

        #self.createDeployment()

    #not working yet.  have to figure out how to "inject" a status into existing body.
    #def update_status(self, newStatus):
        #currentConfig = get_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.watcherApplicationName)
        #Check by printing this.  
        #Overwrite the "status"
        #currentConfig.metadata.status = newStatus

        #Patch the actual resource.
        #api_response = patch_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.customKind, self.watcherApplicationName, currentConfig)
        #return api_response
    
    # def check_marked_for_delete(self):
    #     try:
    #         currentConfig = get_custom_resource(self.apiInstance, self.customGroup, self.customVersion, self.customPlural, self.watcherApplicationName)
    #         self.deleteTimestamp = currentConfig['metadata']['deletionTimestamp']
    #         return True
    #     except:
    #         self.deleteTimestamp = None
    #         return False
        
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

     

   
