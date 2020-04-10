
from pprint import pprint
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

class customResource():
    
def build_api_instance(authorizedClient):
    apiInstance = client.CustomObjectsApi(authorizedClient)
    return apiInstance

def check_for_custom_resource(authorizedClient, operandName, customGroup, customVersion, customPlural):
    apiInstance = build_api_instance(authorizedClient)

    try:
        api_response = apiInstance.get_cluster_custom_object(customGroup, customVersion, customPlural, operandName)
        if api_response['metadata']['name'] == operandName:
            return True    
        else:
            return False                                                 
    except:
        return False
        logger.info("CustomResource not found. No error, just return False.")


def get_custom_resource(authorizedClient, operandName, customGroup, customVersion, customPlural ):
    apiInstance = build_api_instance(authorizedClient)

    try:
        api_response = apiInstance.get_cluster_custom_object(customGroup, customVersion, customPlural, operandName)
        return api_response                                                      
    except ApiException as e:
        logger.error("CustomResource not found. [CustomResource: " + operandName + "] [GET] Error: %s\n" % e)

def patch_custom_resource(authorizedClient, customGroup, customVersion, customPlural, operandName, operandBody):
    

    try:
        apiInstance = build_api_instance(authorizedClient)
        api_response = apiInstance.patch_cluster_custom_object(customGroup, 
                                                        customVersion, 
                                                        customPlural, 
                                                        operandName,
                                                        operandBody)
        return api_response                                                
    except ApiException as e:
        logger.error("CustomResource not patched. [CustomResource: " + operandName + "] [PATCH] Error: %s\n" % e)

