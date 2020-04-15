"""
Creates, updates, and deletes a deployment using AppsV1Api.
"""
import logging

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

def build_api_instance(authorizedClient):
    apiInstance = client.RbacAuthorizationV1Api(authorizedClient)
    return apiInstance

def create_quick_clusterrole_definition(clusterRoleName, rules, annotationsDict={}):

    crRules = client.V1PolicyRule(
        api_groups=["*"],
        resources=["*"],
        verbs=["get","list", "create", "update", "delete", "deletecollection", "watch" ]
    )
    print("CR Rules: " + str(crRules))
    clusterRole = client.V1ClusterRole(
        api_version="rbac.authorization.k8s.io/v1",
        kind="ClusterRole",
        metadata=client.V1ObjectMeta(name= clusterRoleName, annotations=annotationsDict),
        rules=[crRules]
    )

    return clusterRole


def create_clusterrole(apiInstance, crBody):

    try:
        api_response = apiInstance.create_cluster_role(body=crBody)
    except ApiException as e:
        logger.error("Clusterrole not created. [CREATE] Error: %s\n" % e)

def update_clusterrole(apiInstance, crName, crBody):
    try:
        api_response = apiInstance.patch_cluster_role(name=crName,body=crBody)
    except ApiException as e:
        logger.error("Clusterrole not patched. [Clusterrole: " + crName + "] [PATCH] Error: %s\n" % e)

def delete_clusterrole(apiInstance, crName):
        
    deleteBody = client.V1DeleteOptions() # V1DeleteOptions |  (optional)

    try:
        api_response = apiInstance.delete_cluster_role(name=crName, body=deleteBody)
    except ApiException as e:
        logger.error("Clusterrole not deleted. [Clusterrole: " + crName + "] [DELETE] Error: %s\n" % e)

def check_for_clusterrole(apiInstance, crName):
    try:
        api_response = apiInstance.read_cluster_role(name=crName)
        return True
    except ApiException as e:
        return False


def create_quick_clusterrolebinding_definition(clusterRoleBindingName, clusterRoleName, serviceAccountName, saNamespace, annotationsDict={}):

    clusterrole = client.V1RoleRef(
        api_group="rbac.authorization.k8s.io",
        kind="ClusterRole",
        name=clusterRoleName
    )
    subjectsList = client.V1Subject( 
        kind="ServiceAccount",
        name=serviceAccountName,
        namespace=saNamespace 
    )
    clusterRoleBinding = client.V1ClusterRoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="ClusterRoleBinding",
        metadata=client.V1ObjectMeta(name= clusterRoleBindingName, annotations=annotationsDict),
        role_ref=clusterrole,
        subjects=[subjectsList]
    )
    return clusterRoleBinding    

def create_clusterrolebinding(apiInstance, crBindingBody):
    try:
        api_response = apiInstance.create_cluster_role_binding(body=crBindingBody)
    except ApiException as e:
        logger.error("Clusterrolebinding not created. [ClusterroleBinding] [CREATE] Error: %s\n" % e)
        logger.error("Clusterrolebinding YAML: " + str(crBindingBody))

def update_clusterrolebinding(apiInstance, crBindingName, crBindingBody):
    try:
        api_response = apiInstance.patch_cluster_role_binding(name=crBindingName,body=crBindingBody)
    except ApiException as e:
        logger.error("Clusterrolebinding not patched. [ClusterroleBinding: " + crBindingName + "] [PATCH] Error: %s\n" % e)

def delete_clusterrolebinding(apiInstance, crBindingName):
    try:
        deleteBody = client.V1DeleteOptions() # V1DeleteOptions |  (optional)

        api_response = apiInstance.delete_cluster_role_binding(name=crBindingName, body=deleteBody)
        #api_response = apiInstance.delete_cluster_role_binding(name=crBindingName)
    except ApiException as e:
        logger.error("Clusterrolebinding not deleted. [ClusterroleBinding: " + crBindingName + "] [DELETE] Error: %s\n" % e)

def check_for_clusterrolebinding(apiInstance, crBindingName):
    try:
        api_response = apiInstance.read_cluster_role_binding(name=crBindingName)
        return True
    except ApiException as e:
        return False
    
