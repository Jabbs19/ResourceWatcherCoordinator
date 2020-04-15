# ResourceWatcherCoordinator
ResourceWatcher Coordinator (Operator)


## Todo

Move CRD values (jabbs19.com, v1, resourcewatcher, etc.) to input parameters to the python3 application start.  Removes configs, and allows upgrade

Figure out what to do with COnfigMaps (how would a user modifiy it?  Shoudl we just monitor for certain configmaps, then flip to secrets to be mounted?  dual operators?)

Get and Set finalizer 
User doesn't need to include it in the initial CRD, it can just be added when its first found and successfully deployed.

Testing of deployment or all objects to ensure its actually "running"?