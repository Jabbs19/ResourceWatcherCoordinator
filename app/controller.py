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
logging.basicConfig(level=logging.INFO)


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

        self.config_watcher = config_watcher
        #self.config_watcher.add_handler(self._handle_watcherConfig_event)
        self.config_watcher.add_handler(self._handle_event)


        self.deployment_watcher = deployment_watcher
        #self.deployment_watcher.add_handler(self._handle_deploy_event)
        self.deployment_watcher.add_handler(self._handle_event)

       

        #To Add
        self.serviceaccount_watcher = serviceaccount_watcher
        self.serviceaccount_watcher.add_handler(self._handle_event)

        self.clusterrole_watcher = clusterrole_watcher
        self.clusterrole_watcher.add_handler(self._handle_event)
        
        self.clusterroleibnding_watcher = clusterroleibnding_watcher
        self.clusterroleibnding_watcher.add_handler(self._handle_event)                

        #This is the rwCoordinator Object right now.  Has all variables from that config (AuthorizedClient, Group, Plural, Filters, etc)
        self.coordinatorObject = coordinatorObject
        self.crdObject = crdObject

    def _handle_event(self,event):
        
        #New Event Object
        eo = eventObject(event)


        #Queue event object
        self._queue_work(eo)
    def _queue_work(self, eventObject):
        """Add a object name to the work queue."""
        if eventObject.eventObjectType == None:
            logger.error("Invalid eventObject ObjectType: {:s}".format(eventObject.eventObjectType))
            return
        self.workqueue.put(eventObject)

    def run(self):
        """Dequeue and process objects from the `workqueue`. This method
           should not be called directly, but using `start()"""
        self.running = True
        logger.info('Controller starting')
        while self.running:
            eo = self.workqueue.get()
            if not self.running:
                self.workqueue.task_done()
                break
            try:
                print("Reconcile state")
                
                self._process_event(eo)

                #self._printQueue(eo)
                self.workqueue.task_done()
            except Exception as e:
                logger.error("Error _reconcile state {:s}".format(e),exc_info=True)

    def stop(self):
        """Stops this controller thread"""
        self.running = False
        self.workqueue.put(None)


    def _printQueue(self, eventObject):
        """Make changes to go from current state to desired state and updates
           object status."""

        #eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")
        #ns = object_key.split("/")

        print("eventObject.eventObjectType: " + eventObject.eventObjectType)
        print("eventObject.objectName: " + eventObject.objectName)
        print("eventObject.objectNamespace: " + eventObject.objectNamespace)
        #print("eventObject.object 'object': " + str(eventObject.fullEventObject))

    def _process_event(self, eventObject):
        """Make changes to go from current state to desired state and updates
           object status."""
        #Can remove this logging later, not using event key anymore.
        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
            "Event found."))  


        if eventObject.eventType in ['DELETED']:

            process_deleted_event(eventObject)

        else:

            if should_event_be_processed(eventObject, self.crdObject, self.coordinatorObject):
                operand = load_configuration_operand(eventObject, self.crdObject, self.coordinatorObject)
                logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                    "Event Processing."))   
            
                rw = resourceWatcher(operand, self.coordinatorObject.childAnnotationFilterKey)

                if check_marked_for_delete(eventObject, self.crdObject, self.coordinatorObject):

                    process_marked_for_deletion(eventObject, self.crdObject, self.coordinatorObject, rw)

                else: 

                    if eventObject.eventType in ['ADDED']:

                        process_added_event(eventObject, self.crdObject, self.coordinatorObject, rw)

                    
                    elif eventObject.eventType in ['MODIFIED']:
                        
                        process_modified_event(eventObject, self.crdObject, self.coordinatorObject, rw)

                    else:
                        logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                            "Event found, but did not match any filters."))  
            
            else:
                logger.info("[ObjectType: %s] [ObjectName: %s] [Namespace: %s] [EventType: %s] [Message: %s]" % (eventObject.eventObjectType, eventObject.objectName, eventObject.objectNamespace, eventObject.eventType, 
                    "Event Not Processed.")) 


    # def _process_event(self, object_key):
    #     """Make changes to go from current state to desired state and updates
    #        object status."""
    #     logger.info("Event Pulled from Queue: {:s}".format(object_key))
    #     eventType, eventObject, objectName, objectNamespace, annotationValue = object_key.split("~~")

    #     if eventType in ['DELETED']:
    #         logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #             "Event found."))                     
            
    #         process_deleted_event(object_key)
        
    #     else:

    #         #Load the operand and whether or not we should continue.
    #         rwOperand, should_event_be_processed = load_configuration_object(object_key, self.crdObject, self.coordinatorObject)

            
    #         if should_event_be_processed:
    #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                     "ResourceWatcher found."))            


    #             # Check to see if it's been "marked for deletion"
    #             if check_marked_for_delete(object_key, self.crdObject, self.coordinatorObject):
    #                 logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                         "ResourceWacher marked for deletion."))  

    #                 process_marked_for_deletion(object_key, self.crdObject, self.coordinatorObject, rw)

    #             else:

    #                 if eventType in ['ADDED']:
    #                     logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                         "Event found.")) 
                        
    #                     process_added_event(object_key, self.crdObject, self.coordinatorObject, rw)

    #                 elif eventType in ['MODIFIED']:
    #                     logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                         "Event found.")) 

    #                     process_modified_event(object_key, self.crdObject, self.coordinatorObject, rw)
    #                 else:
    #                     logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                         "Event found, but did not match any filters."))                        
            
    #         else:
    #             logger.info("[ObjectType: %s][ObjectName: %s][Namespace: %s][EventType: %s][Annotation: %s][Message: %s]" % (eventObject, objectName, objectNamespace, eventType, annotationValue,
    #                         "No ResourceWatcher found."))  
               
          
