
from pprint import pprint
from kubernetes import client, config
from kubernetes.client.rest import ApiException

def check_for_custom_resource(apiInstance, customGroup, customVersion, customPlural, crName):

    try:
        api_response = apiInstance.get_cluster_custom_object(customGroup, customVersion, customPlural, crName)
        if api_response['metadata']['name'] == crName:
            return True    
        else:
            return False                                                 
    except:
        return False
        print("Error with this")

def get_custom_resource(apiInstance, customGroup, customVersion, customPlural, crName):

    try:
        api_response = apiInstance.get_cluster_custom_object(customGroup, customVersion, customPlural, crName)
        return api_response                                                      
    except ApiException as e:
        print("Exception customresources->get_custom_resource: %s\n" % e)     

def patch_custom_resource(apiInstance, customGroup, customVersion, customPlural, customKind, crName, crBody):
    
    try:
        api_response = apiInstance.patch_cluster_custom_object(customGroup, 
                                                        customVersion, 
                                                        customPlural, 
                                                        crName,
                                                        crBody)
        return api_response                                                
    except ApiException as e:
        print("Exception customresources->patch_cluster_custom_object: %s\n" % e)     


