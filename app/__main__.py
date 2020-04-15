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


logger = logging.getLogger('main')
logging.basicConfig(level=logging.INFO)

PARSER = argparse.ArgumentParser()
PARSER.add_argument("--tester")

def main():

    load_cluster_config()
    
    authorizedClient = create_authorized_client()

    #Pass these values in as part of Start Command.  Allows for upgrades.
    rwCRD = crd("jabbs19.com","v1","resourcewatchers","ResourceWatcher")
    rwCoordinator = coordinator(authorizedClient)

    args = PARSER.parse_args()
    print(str(args.tester))

    if args.tester == "serviceaccount":
        print("Test Mode (SA)")
        body = create_quick_sa_definition("mj-with-annotations", "resource-watcher-testnamespace", {"resourceWatcherParent":"resource-watcher-serviceb"})
        create_serviceaccount(rwCoordinator.coreAPI, body, "resource-watcher-testnamespace")
    elif args.tester == "clusterrole":
        body = create_quick_clusterrole_definition("mj-test-clusterrole","blahblah")
        create_clusterrole(rwCoordinator.coreAPI, body)
    elif args.tester == "clusterrolebinding":
        body = create_quick_clusterrolebinding_definition("mj-test-clusterrolebinding", "mj-test-clusterrole", "mj-test-sa", "resource-watcher-testnamespace")
        create_clusterrolebinding(rwCoordinator.coreAPI, body)
    elif args.tester == "configmap":
        cmBody = create_quick_configmap_definition('mj-test', "resource-watcher-testnamespace",{"resourceWatcherParent":"resource-watcher-serviceb"})
        create_config_map(rwCoordinator.coreAPI,cmBody, "resource-watcher-testnamespace")

    else:
        #Primary CR/Operand Watcher
        cr_watcher = ThreadedWatcher(rwCoordinator.customEventFilter,rwCoordinator.customApiInstance.list_cluster_custom_object, 
                                                rwCRD.customGroup, 
                                                rwCRD.customVersion, 
                                                rwCRD.customPlural)

        #Primary deployed object Watcher
        deployment_watcher = ThreadedWatcher(rwCoordinator.deployEventFilter, rwCoordinator.deploymentApiInstance.list_deployment_for_all_namespaces)

        #Secondary "Monitor" watchers.  Essentially, if Modified, redeploy entire application.
        serviceaccount_watcher = ThreadedWatcher(rwCoordinator.coreAPIfilter, rwCoordinator.coreAPI.list_service_account_for_all_namespaces)
        clusterrole_watcher = ThreadedWatcher(rwCoordinator.rbacAPIfilter, rwCoordinator.rbacAPI.list_cluster_role)
        clusterrolebinding_watcher = ThreadedWatcher(rwCoordinator.rbacAPIfilter, rwCoordinator.rbacAPI.list_cluster_role_binding)


        #Controller.  All "watchers" fed into Controller to process queues.
        controller = Controller(rwCRD, rwCoordinator, deployment_watcher, cr_watcher, serviceaccount_watcher, clusterrole_watcher, clusterrolebinding_watcher)
        controller.start()
   
        cr_watcher.start()

        deployment_watcher.start()

        serviceaccount_watcher.start()
        clusterrole_watcher.start()
        clusterrolebinding_watcher.start()

        try:
            controller.join()

        except (KeyboardInterrupt, SystemExit):
            print('\n! Received keyboard interrupt, quitting threads.\n')
            controller.stop()
            controller.join()


if __name__ == '__main__':
    main()
