import argparse
import logging
import sys
import os

from kubernetes import client, config
#from .watcher import *

from  .defs import *
from .controller import Controller
from .threadedwatch import ThreadedWatcher
from .coordinator import *
from .simpleclient import *

#for testing
from .rbac import *


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

PARSER = argparse.ArgumentParser()
PARSER.add_argument("--tester")

def main():

    load_cluster_config()
    
    authorizedClient = create_authorized_client()

    rwCoordinator = coordinator(authorizedClient)


    #Load Config.  Needs to pass kubeconfig location?

    #print(str(rwCoordinator.customGroup))

    # customAPI = create_api_client(rwCoordinator.customApiVersion,authorizedClient)
    # deployAPI = create_api_client(rwCoordinator.deploymentApiVersion,authorizedClient)
    # rwCoordinator.set_api_instance(customApiInstance=customAPI, deploymentApiInstance=deployAPI)

    #Get API Instances for ThreadWatchers
    rwCoordinator.autobuild_api_instances()

    args = PARSER.parse_args()
    print(str(args.tester))

    if args.tester == "serviceaccount":
        print("Test Mode (SA)")
        body = create_quick_sa_definition("mj-test-sa", "resource-watcher-testnamespace")
        create_serviceaccount(create_api_client("CoreV1Api",authorizedClient), body, "resource-watcher-testnamespace")
    elif args.tester == "clusterrole":
        body = create_quick_clusterrole_definition("mj-test-clusterrole","blahblah")
        create_clusterrole(create_api_client("RbacAuthorizationV1Api",authorizedClient), body)
    elif args.tester == "clusterrolebinding":
        body = create_quick_clusterrolebinding_definition("mj-test-clusterrolebinding", "mj-test-clusterrole", "mj-test-sa", "resource-watcher-testnamespace")
        create_clusterrolebinding(create_api_client("RbacAuthorizationV1Api",authorizedClient), body)
    else:
   
        #Primary CR/Operand Watcher
        cr_watcher = ThreadedWatcher(rwCoordinator.customEventFilter,rwCoordinator.customApiInstance.list_cluster_custom_object, 
                                                rwCoordinator.customGroup, 
                                                rwCoordinator.customVersion, 
                                                rwCoordinator.customPlural)

        #Primary deployed object Watcher
        deployment_watcher = ThreadedWatcher(rwCoordinator.deployEventFilter, rwCoordinator.deploymentApiInstance.list_deployment_for_all_namespaces)
        
        #Secondary "Monitor" watchers.  Essentially, if Modified, redeploy entire application.
        serviceaccount_watcher = ThreadedWatcher(rwCoordinator.coreAPIfilter, rwCoordinator.coreAPI.list_service_account_for_all_namespaces)

        #Controller.  All "watchers" fed into Controller to process queues.
        controller = Controller(rwCoordinator, deployment_watcher, cr_watcher, serviceaccount_watcher)
        controller.start()
        
        cr_watcher.start()

        deployment_watcher.start()

        serviceaccount_watcher.start()
        
        try:
            controller.join()
        except (KeyboardInterrupt, SystemExit):
            print('\n! Received keyboard interrupt, quitting threads.\n')
            controller.stop()
            controller.join()


if __name__ == '__main__':
    main()