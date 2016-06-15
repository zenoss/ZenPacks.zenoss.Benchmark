

from Products.AdvancedQuery import Eq, MatchGlob, And

from Products.ZenHub.HubService import HubService
from Products.ZenHub.PBDaemon import translateError
from Products.Zuul.interfaces import ICatalogTool

import logging
import random

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
        results = cat.search(query=query, limit=200)
        pairs = []
        if results.total:
            for brain in results.results:
                device_name = brain.id
                device = brain.getObject()
                component_name = ""
                if hasattr(device, "componentSearch"):
                    component_brains = device.componentSearch()
                    if component_brains:
                        component_name = random.choice(component_brains).id
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
