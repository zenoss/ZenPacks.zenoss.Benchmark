#! /usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


__doc__ = """zenmodelerbench

Write simulated datamaps to ZenHub at a given rate.

"""
import os.path
import sys
import logging
import struct
import socket
import random
import md5
import os
import cPickle

from twisted.internet import reactor, defer
import twisted.python.log

import Globals
import zope.interface
import zope.component

from Products.DataCollector.DeviceProxy import DeviceProxy
from Products.ZenCollector.daemon import CollectorDaemon
from Products.ZenCollector.interfaces import ICollector, ICollectorPreferences,\
    IEventService, \
    IScheduledTask, \
    IStatisticsService

from Products.ZenCollector.tasks import NullTaskSplitter,\
    BaseTask, TaskStates

from Products.ZenEvents.EventServer import Stats
from twisted.python.failure import Failure
from Products.ZenUtils.Utils import unused
from Products.ZenCollector.services.config import DeviceProxy
from Products.ZenCollector.daemon import DUMMY_LISTENER
from Products.DataCollector.plugins.DataMaps import ObjectMap

import time

here = lambda *x: os.path.join(os.path.dirname(__file__), *x)

unused(Globals, DeviceProxy)

COLLECTOR_NAME = 'zenmodelerbench'
log = logging.getLogger("zen.%s" % COLLECTOR_NAME)


class ModelerBenchPreferences(object):
    zope.interface.implements(ICollectorPreferences)

    def __init__(self):
        """
        Constructs a new ModelerBenchPreferences instance and
        provides default values for needed attributes.
        """
        self.collectorName = COLLECTOR_NAME
        self.configCycleInterval = 20  # minutes
        self.cycleInterval = 5 * 60  # seconds

        # The configurationService attribute is the fully qualified class-name
        # of our configuration service that runs within ZenHub
        self.configurationService = 'NullConfig'

        # Will be filled in based on buildOptions
        self.options = None

        self.configCycleInterval = 20*60

    def postStartupTasks(self):
        return []

    def buildOptions(self, parser):
        """
        Command-line options to be supported
        """
        parser.add_option('--stats', dest='stats',
                          action='store_true', default=False,
                          help='Print statistics to log every 2 secs')

        parser.add_option('--datamapdir', dest='datamapdir',
                          default='./data/medium',
                          help='Directory containing datamaps')

        # Not used for now
        parser.add_option('--rate',
                          dest='datamaprate',
                          default=5.,
                          type='float',
                          help='Datamaps per second to publish to zenhub')

    def postStartup(self):
        # add our collector's custom statistics
        statService = zope.component.queryUtility(IStatisticsService)
        statService.addStatistic("events", "COUNTER")


def random_ip():
    return socket.inet_ntoa(struct.pack('>I', random.randint(1, 0xffffffff)))


RANDOM_MASKS = [16, 18, 20, 24, 26, 28]


def random_mask():
    return random.choice(RANDOM_MASKS)


def random_id():
    return md5.md5(os.urandom(20)).hexdigest()[:10]


def hack_interface_data(data_maps):
    for data_map in data_maps:
        for object_map in data_map.maps:
            if "setIpAddresses" in object_map._attrs:
                ip = random_ip()
                mask = random_mask()
                object_map.setIpAddresses = [ "{0}/{1}".format(ip, mask) ] # RANDOM IP

    return data_maps


def hack_maps(maps):
    """ Hack the interfaces map to inject random ips """
    hacked_maps = []
    for map_file_name, maps in maps.iteritems():
        if "zenoss.snmp.InterfaceMap.processed.pickle" in map_file_name:
            maps = hack_interface_data(maps)
        hacked_maps.extend(maps)
    return hacked_maps


def load_maps(maps_path):
    maps = {}
    for fname in os.walk(here(maps_path)).next()[2]:
        with open(here(maps_path, fname)) as f:
            maps[fname] = cPickle.load(f)
    return maps


class ZenModelerBenchDaemon(CollectorDaemon):

    def __init__(self, preferences, taskSplitter,
                 configurationListener=DUMMY_LISTENER,
                 initializationCallback=None,
                 stoppingCallback=None):
        self.initialServices += ['DiscoverService']
        super(ZenModelerBenchDaemon, self).__init__(preferences, taskSplitter,
                                                    configurationListener,
                                                    initializationCallback,
                                                    stoppingCallback)
        self.devices_processed = 0
        self.maps = load_maps(self.options.datamapdir)

    @defer.inlineCallbacks
    def publishLoop(self):
        yield self.publish()
        # For now we only send another device once the previous one has finished
        # to measure how low took the hub to process the applydatamap call
        #
        reactor.callLater(0, self.publishLoop)

    def config(self):
        return self.services.get('DiscoverService')

    @defer.inlineCallbacks
    def publish(self):
        d_name = random_id()
        d_ip = random_ip()
        result = yield self.config().callRemote("createDevice", d_ip,
                    deviceName=d_name, devicePath="/Server/Linux")

        if isinstance(result, Failure):
            self.log.exception("Unable to create device")
            return
        dev, created = result
        id_ = dev.getId()
        hacked_maps = hack_maps(self.maps) # create random ips
        start = time.time()
        x = yield self.config().callRemote("applyDataMaps", id_, hacked_maps)
        duration = time.time()-start
        self.log.info("ApplyDataMaps took {0} seconds for device {1} / {2}".format(duration, d_name, d_ip))
        self.rrdStats.gauge('zenmodelerbench.applyDataMaps', duration)
        self.devices_processed = self.devices_processed + 1


    def run(self):
        threshold_notifier = self._getThresholdNotifier()
        self.rrdStats.config(self.name,
                             self.options.monitor,
                             self.metricWriter(),
                             threshold_notifier,
                             self.derivativeTracker())
        self.log.debug('Starting PBDaemon initialization')
        d = self.connect()

        def callback(result):
            self.sendEvent(self.startEvent)
            self.publishLoop()
            self.log.debug('Calling connected.')
            self.connected()
            return result

        d.addCallback(callback)
        d.addErrback(twisted.python.log.err)
        reactor.run()
        if self._customexitcode:
            sys.exit(self._customexitcode)


if __name__ == '__main__':
    myPreferences = ModelerBenchPreferences()
    myTaskSplitter = NullTaskSplitter()
    daemon = ZenModelerBenchDaemon(myPreferences, myTaskSplitter)
    daemon.run()
