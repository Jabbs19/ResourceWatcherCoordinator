import argparse
import logging
import sys
import os

from kubernetes import client, config
#from .watcher import *

from  .defs import *
from .controller import Controller
from .threadedwatch import ThreadedWatcher
from .watcher import *
from .operator import *
from .simpleclient import *


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def main():

    #Installation Configurations Used:
    #Move to Helm, hardcode, etc?  For now, leave variables to re-use this code.
    vCustomAPI = "CustomObjectsApi"
    vDeployAPI = "AppsV1Api"
    vCustomGroup = "jabbs19.com"
    vCustomVersion = "v1"
    vCustomPlural = "watcherconfigs"
    vCustomKind = "WatcherConfig"
    vApiVersion = "CoreV1Api"
    vCustomEventFilter =  {'eventTypesList': ['ADDED','MODIFIED','DELETED']}
    vDeployEventFilter = {'eventTypesList': ['MODIFIED']}
    vFinalizer = ['watcher.delete.finalizer']

    #Load Config.  Needs to pass kubeconfig location?
    process_kubeconfig()

    authorizedClient = create_authorized_client()
    customAPI = create_api_client(vCustomAPI,authorizedClient)
    deployAPI = create_api_client(vDeployAPI,authorizedClient)

    #
    #WatcherOperatorConfig "Master" Configuration (Could be configmap, secret, helm values, etc.)
    #Change into CRD, run an "install Pod" to do upgrades, installs, etc.

    #Operator Config
    watchOpConfig = watcherOperatorConfig()
    
    deployment_watcher = ThreadedWatcher(deployAPI.list_deployment_for_all_namespaces, vDeployEventFilter)


    #Application Configs

    cr_watcher = ThreadedWatcher(customAPI.list_cluster_custom_object, 
                                            vCustomEventFilter,
                                            vCustomGroup, 
                                            vCustomVersion, 
                                            vCustomPlural)

    controller = Controller(deployment_watcher, config_watcher, deployAPI, customAPI,
                                            watchOpConfig,
                                            vCustomEventFilter,
                                            vCustomGroup, 
                                            vCustomVersion, 
                                            vCustomPlural)


    controller.start()
    deployment_watcher.start()
    config_watcher.start()
    try:
        controller.join()
    except (KeyboardInterrupt, SystemExit):
        print('\n! Received keyboard interrupt, quitting threads.\n')
        controller.stop()
        controller.join()


if __name__ == '__main__':
    main()
