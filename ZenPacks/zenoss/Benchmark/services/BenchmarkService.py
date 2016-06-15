

from Products.AdvancedQuery import Eq, MatchGlob, And

from Products.ZenHub.HubService import HubService
from Products.ZenHub.PBDaemon import translateError
from Products.Zuul.interfaces import ICatalogTool

import logging

log = logging.getLogger("zenoss.Benchmark")

class BenchmarkService(HubService):

    @translateError
    def remote_getDeviceComponentPairs(self):
        """
        return tuple (device, device_component) in order to be able to generate 
        more realistic events

        """
        cat = ICatalogTool(self.dmd)
        query = Eq('objectImplements', "Products.ZenModel.Device.Device")
        results = cat.search(query=query, limit=100)
        pairs = []
        if results.total:
            for brain in results.results:
                device_name = brain.id
                device_path = brain.getPath()
                query = [ Eq('objectImplements', "Products.ZenModel.DeviceComponent.DeviceComponent") ]
                query.append( MatchGlob("path", "{0}/os/".format(device_path)) )
                components_search = cat.search(query=And(*query), limit=1)
                if components_search.total:
                    component_name = components_search.results.next().id
                    pairs.append( (device_name, component_name) )
        return pairs

    @translateError
    def remote_getDeviceClasses(self):
        device_classes = []
        cat = ICatalogTool(self.dmd)
        query = Eq('objectImplements', "Products.ZenModel.DeviceClass.DeviceClass")
        results = cat.search(query=query)
        if results.total:
            for brain in results.results:
                try:
                    dc = brain.getPath()[18:] # strip /zport/dmd/Devices
                except:
                    pass
                else:
                    if dc:
                        device_classes.append(dc)
        return device_classes

    @translateError
    def remote_getEventClasses(self):
        event_classes = []
        cat = ICatalogTool(self.dmd)
        query = Eq('objectImplements', "Products.ZenEvents.EventClass.EventClass")
        results = cat.search(query=query)
        if results.total:
            for brain in results.results:
                try:
                    ec = brain.getPath()[17:] # strip /zport/dmd/Events
                except:
                    pass
                else:
                    if ec and 'Heartbeat' not in ec:
                        event_classes.append(ec)
        return event_classes
