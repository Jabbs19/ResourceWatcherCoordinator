import logging
import queue
import threading

from kubernetes.client.rest import ApiException
from kubernetes.client import models
from kubernetes import client, config
import copy
from .deployments import *
from .customresources import *
from .coordinator import *


logger = logging.getLogger('controller')


class Controller(threading.Thread):
    """Reconcile current and desired state by listening for events and making
       calls to Kubernetes API.
    """

    def __init__(self, crdObject, coordinatorObject, deployment_watcher, config_watcher, serviceaccount_watcher, clusterrole_watcher, clusterroleibnding_watcher,workqueue_size=25):
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
        self.deployment_watcher = deployment_watcher
        self.deployment_watcher.add_handler(self._handle_deploy_event)
        self.config_watcher = config_watcher
        self.config_watcher.add_handler(self._handle_watcherConfig_event)

        #To Add
        self.serviceaccount_watcher = serviceaccount_watcher
        self.serviceaccount_watcher.add_handler(self._handle_agnostic_event)

        self.clusterrole_watcher = clusterrole_watcher
        self.clusterrole_watcher.add_handler(self._handle_agnostic_event)
        
        self.clusterroleibnding_watcher = clusterroleibnding_watcher
        self.clusterroleibnding_watcher.add_handler(self._handle_agnostic_event)                

        #This is the rwCoordinator Object right now.  Has all variables from that config (AuthorizedClient, Group, Plural, Filters, etc)
        self.coordinatorObject = coordinatorObject
        self.crdObject = crdObject

    def _handle_agnostic_event(self,event):
        
        eventType = event['type']
        try:
            eventObject = event['object'].kind
        except:
            eventObject = event['object']['kind']

        try:
            objectName = event['object'].metadata.name
        except:
            objectName = event['object']['metadata']['name']

        try:
            objectNamespace = event['object'].metadata.namespace
        except:
            objectNamespace = event['object']['metadata']['namespace']
        if objectNamespace == None:
            objectNamespace = 'GLOBAL'            

        try:
            annotationsDict = event['object'].metadata.annotations
        except:
            annotationsDict = event['object']['metadata']['annotations']

        try:
            eventObject = event['object'].kind
        except:
            eventObject = event['object']['kind']

        annotationValue = get_annotation_value(self.coordinatorObject.annotationFilterKey, annotationsDict)

        if annotationValue == None:
            annotationValue = "NONE"

        self._queue_work(eventType + "~~" + eventObject + "~~" + objectName + "~~" + objectNamespace + "~~" + annotationValue )


    def _handle_deploy_event(self, event):
        """Handle an event from the deployment.  Send to `workqueue`. """
        #logging.info("Event Found: %s %s %s" % (event['type'], event['object'].kind, event['object'].metadata.name)) 

        eventType = event['type']
        #eventObject = event['object']['kind']
        eventObject = event['object'].kind
        #name = event['object']['metadata']['name']
        deploymentName = event['object'].metadata.name
        #deployNamespace = event['object']['metadata']['namespace']
        deploymentNamespace = event['object'].metadata.namespace
        annotationValue = 'nothing yet'
        
        self._queue_work(eventType + "~~" + eventObject + "~~" + deploymentName + "~~" + deploymentNamespace + "~~" + annotationValue )
        #self._queue_work(name)

    def _handle_watcherConfig_event(self, event):
        """Handle an event from the watcherConfig.  Send to `workqueue`."""

        eventType = event['type']
        eventObject = event['object']['kind']
        resourceWatcherName = event['object']['metadata']['name']
        #M
        resourceWatcherDeployedNamespace = event['object']['spec']['deployNamespace']
        annotationValue = 'nothing yet'

        self._queue_work(eventType + "~~" + eventObject + "~~" + resourceWatcherName + "~~" + resourceWatcherDeployedNamespace + "~~" + annotationValue )
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
                self._process_event(e)
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

        eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")
        #ns = object_key.split("/")

        print("eventType: " + eventType)
        print("eventObject: " + eventObject)
        print("objectNamespace: " + objectNamespace)
        print("objectName: " + objectName)
        print("annotationValue: " + annotationValue)


    def _process_event(self, object_key):
        """Make changes to go from current state to desired state and updates
           object status."""
        logger.info("Event Found: {:s}".format(object_key))
        eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

        if eventType in ['DELETED']:
            logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                "Event found."))                     
            
            process_deleted_event(object_key)
        
        else:

            #Load the operand and whether or not we should continue.
            rwOperand, should_event_be_processed = load_configuration_object(self.coordinatorObject.authorizedClient, object_key, self.coordinatorObject.customGroup, self.coordinatorObject.customVersion, self.coordinatorObject.customPlural)

            
            if should_event_be_processed:
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                        "ResourceWatcher found."))            

                rw = resourceWatcher( rwOperand, self.coordinatorObject)

                # Check to see if it's been "marked for deletion"
                if check_marked_for_delete(self.coordinatorObject.authorizedClient, object_key, self.coordinatorObject.customGroup, self.coordinatorObject.customVersion, self.coordinatorObject.customPlural):
                    logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                            "ResourceWacher marked for deletion."))  

                    rw.process_marked_for_deletion(object_key)

                else:

                    if eventType in ['ADDED']:
                        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                            "Event found.")) 
                        
                        rw.process_added_event(object_key)

                    elif eventType in ['MODIFIED']:
                        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                            "Event found.")) 

                        rw.process_modified_event(object_key)
                    else:
                        logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                            "Event found, but did not match any filters."))                        
            
            else:
                logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
                            "No ResourceWatcher found."))  
               
          


        #     else:
        #         if eventType in ['ADDED']:
        #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType,
        #                 "Event found.")) 
        #             if check_for_deployment(self.deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace):
        #                 dep = watcherApplicationConfig.get_deployment_object()
        #                 update_deployment(self.deployAPI, dep, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace)
        #                 #watcherApplicationConfig.updateStatus(objectName, 'Added')

        #             else:
        #                 dep = watcherApplicationConfig.get_deployment_object()
        #                 create_deployment(self.deployAPI, dep, watcherApplicationConfig.deployNamespace)
        #             #self.createDeployment()
        #         elif eventType in ['MODIFIED']:
        #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType,
        #                 "Event found.")) 
        #             if check_for_deployment(self.deployAPI, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace):
        #                 dep = watcherApplicationConfig.get_deployment_object()
        #                 update_deployment(self.deployAPI, dep, watcherApplicationConfig.watcherApplicationName, watcherApplicationConfig.objectNamespace)
        #                 #watcherApplicationConfig.updateStatus(objectName, 'Added and Modified')

        #             else:
        #                 dep = watcherApplicationConfig.get_deployment_object()
        #                 create_deployment(self.deployAPI, dep, watcherApplicationConfig.deployNamespace)
        #         elif eventType in ['DELETED']:
        #             #Since only sending "delete" events for custom resource, this is truly once its been deleted. 
        #             #Can't use for deleting deployment.
        #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType,
        #                 "Event found.")) 
        #             #watcherApplicationConfig.updateStatus(objectName, 'Deleted')
        #         else:
        #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType,
        #                 "Event found, but did not match any filters.")) 

        # else:
        #     logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType,
        #                 "No WatcherConfig found."))  


     

   
