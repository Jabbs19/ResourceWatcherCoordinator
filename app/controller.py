import logging
import queue
import threading

from kubernetes.client.rest import ApiException
from kubernetes.client import models
from kubernetes import client, config
import copy
from .deployments import *
from .watcher import *
from .customresources import *


logger = logging.getLogger('controller')


class Controller(threading.Thread):
    """Reconcile current and desired state by listening for events and making
       calls to Kubernetes API.
    """

    def __init__(self, deployment_watcher, config_watcher, deployAPI,
                 customAPI, operatorConfig, customGroup, customVersion, customPlural,
                 customKind, workqueue_size=10):
        """Initializes the controller.

        :param deploy_watcher: Watcher for pods events.
        :param watchConfig_watcher: Watcher for watcherconfig custom
                                           resource events.
        :param deployAPI: kubernetes.client.AppsV1Api()
        :param customAPI: kubernetes.client.CustomObjectsApi()
        :param customGroup: The custom resource's group name
        :param customVersion: The custom resource's version
        :param customPlural: The custom resource's plural name.
        :param customKind: The custom resource's kind name.
        :param workqueue_size: queue size for resources that must be processed.
        """
        super().__init__()
        # `workqueue` contains namespace/name of immortalcontainers whose status
        # must be reconciled
        self.workqueue = queue.Queue(workqueue_size)
        self.authconfiguration = authconfiguration
        self.deployment_watcher = deployment_watcher
        self.config_watcher = config_watcher
        self.deployAPI = deployAPI
        self.customAPI = customAPI
        
        self.customGroup = customGroup
        self.customVersion = customVersion
        self.customPlural = customPlural
        self.customKind = customKind
        self.deployment_watcher.add_handler(self._handle_deploy_event)
        self.config_watcher.add_handler(self._handle_watcherConfig_event)

    def _handle_deploy_event(self, event):
        """Handle an event from the deployment.  Send to `workqueue`. """
        #logging.info("Event Found: %s %s %s" % (event['type'], event['object'].kind, event['object'].metadata.name)) 

        eventType = event['type']
        #eventObject = event['object']['kind']
        eventObject = event['object'].kind
        #name = event['object']['metadata']['name']
        deploymentName = event['object'].metadata.name
        #deployNamespace = event['object']['metadata']['namespace']
        deployNamespace = event['object'].metadata.namespace
        additionalVars = 'nothing yet'
        
        self._queue_work(eventType + "~~" + eventObject + "~~" + deploymentName + "~~" + deployNamespace + "~~" + additionalVars )
        #self._queue_work(name)

    def _handle_watcherConfig_event(self, event):
        """Handle an event from the watcherConfig.  Send to `workqueue`."""

        eventType = event['type']
        eventObject = event['object']['kind']
        configName = event['object']['metadata']['name']
        deployNamespace = event['object']['spec']['deployNamespace']
        additionalVars = 'nothing yet'

        self._queue_work(eventType + "~~" + eventObject + "~~" + configName + "~~" + deployNamespace + "~~" + additionalVars )
       # self._queue_work(name)

    def _queue_work(self, object_key):
        """Add a object name to the work queue."""
        if len(object_key.split("~~")) != 5:
            logger.error("Invalid object key: {:s}".format(object_key))
            return
        self.workqueue.put(object_key)

    def run(self):
        """Dequeue and process objects from the `workqueue`. This method
           should not be called directly, but using `start()"""
        self.running = True
        logger.info('Controller starting')
        while self.running:
            e = self.workqueue.get()
            if not self.running:
                self.workqueue.task_done()
                break
            try:
                #print("Reconcile state")
                self._reconcile_state(e)
                #self._printQueue(e)
                self.workqueue.task_done()
            except Exception as ex:
                logger.error(
                    "Error _reconcile state {:s}".format(e),
                    exc_info=True)

    def stop(self):
        """Stops this controller thread"""
        self.running = False
        self.workqueue.put(None)


    def _printQueue(self, object_key):
        """Make changes to go from current state to desired state and updates
           object status."""

        eventType, eventObject, deployOrConfigName, deployNamespace, additionalVars = object_key.split("~~")
        #ns = object_key.split("/")

        print("EventType: " + eventType)
        print("eventObject: " + eventObject)
        print("deployNamespace: " + deployNamespace)
        print("Name: " + deployOrConfigName)
        print("AdditionalVars: " + additionalVars)


    def _reconcile_state(self, object_key):
        """Make changes to go from current state to desired state and updates
           object status."""
        logger.info("Event Found: {:s}".format(object_key))
        eventType, eventObject, deployOrConfigName, deployNamespace, additionalVars = object_key.split("~~")

        deployAPI = client.AppsV1Api(self.authconfiguration)
        customAPI = client.CustomObjectsApi(self.authconfiguration)
       
        watcherConfigExist = check_for_custom_resource(customAPI, self.customGroup, self.customVersion, self.customPlural, deployOrConfigName)

        if watcherConfigExist == True:
            logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, 
                    "WatcherConfig found."))

            #Get CR (the "Watcher Config")            
            cr = get_custom_resource(customAPI, self.customGroup, self.customVersion, self.customPlural, deployOrConfigName)
            watcherApplicationConfig = watcherApplication(apiInstance=customAPI, crObject=cr, operatorConfig=self.operatorConfig)
            logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, 
                    "WatcherConfig loaded."))
            
            if watcherApplicationConfig.check_marked_for_delete():
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, 
                    "WatcherConfig marked for deletion."))                
                
                delete_deployment(deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.deployNamespace)
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, 
                    "Watcher Deployment deleted.")) 
                
                watcherApplicationConfig.remove_finalizer()
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, 
                    "WatcherConfig deleted.")) 

            else:
                if eventType in ['ADDED']:
                    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, eventType,
                        "Event found.")) 
                    if check_for_deployment(deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.deployNamespace):
                        dep = watcherApplicationConfig.get_deployment_object()
                        update_deployment(deployAPI, dep, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.deployNamespace)
                        #watcherApplicationConfig.updateStatus(deployOrConfigName, 'Added')

                    else:
                        dep = watcherApplicationConfig.get_deployment_object()
                        create_deployment(deployAPI, dep, watcherApplicationConfig.deployNamespace)
                    #self.createDeployment()
                elif eventType in ['MODIFIED']:
                    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, eventType,
                        "Event found.")) 
                    if check_for_deployment(deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.deployNamespace):
                        dep = watcherApplicationConfig.get_deployment_object()
                        update_deployment(deployAPI, dep, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.deployNamespace)
                        #watcherApplicationConfig.updateStatus(deployOrConfigName, 'Added and Modified')

                    else:
                        dep = watcherApplicationConfig.get_deployment_object()
                        create_deployment(deployAPI, dep, watcherApplicationConfig.deployNamespace)
                elif eventType in ['DELETED']:
                    #Since only sending "delete" events for custom resource, this is truly once its been deleted. 
                    #Can't use for deleting deployment.
                    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, eventType,
                        "Event found.")) 
                    #watcherApplicationConfig.updateStatus(deployOrConfigName, 'Deleted')
                else:
                    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, eventType,
                        "Event found, but did not match any filters.")) 

        else:
            logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, deployOrConfigName, deployNamespace, eventType,
                        "No WatcherConfig found."))  


     

   
