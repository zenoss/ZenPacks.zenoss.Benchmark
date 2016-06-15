#! /usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


__doc__ = """zeneventbench

Write simulated events to ZenHub at a given rate.

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

from ZenPacks.zenoss.Benchmark.services.BenchmarkService import BenchmarkService

import time

here = lambda *x: os.path.join(os.path.dirname(__file__), *x)

unused(Globals, DeviceProxy)

COLLECTOR_NAME = 'zeneventbench'
log = logging.getLogger("zen.%s" % COLLECTOR_NAME)


class EventBenchPreferences(object):
    zope.interface.implements(ICollectorPreferences)

    def __init__(self):
        """
        Constructs a new EventBenchPreferences instance and
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


    def postStartupTasks(self):
        return []

    def buildOptions(self, parser):
        """
        Command-line options to be supported
        """
        # Not used for now
        parser.add_option('--rate',
                          dest='event_rate',
                          default=10.0,
                          type='float',
                          help='Events per second to publish to zenhub')

    def postStartup(self):
        # add our collector's custom statistics
        statService = zope.component.queryUtility(IStatisticsService)
        statService.addStatistic("events", "COUNTER")


class ZenEventBenchDaemon(CollectorDaemon):

    def __init__(self, preferences, taskSplitter,
             configurationListener=DUMMY_LISTENER,
             initializationCallback=None,
             stoppingCallback=None):
        self.initialServices += ['ModelerService', 'ZenPacks.zenoss.Benchmark.services.BenchmarkService']
        self.device_component_pairs = None
        self.event_classes = None
        self.loading_devices = False
        self.reload_devices_interval = 10*60 # Every 10 minutes we reload the devices
        self.last_reload = 0
        self.severities = []
        for sev in xrange(0, 6):
            self.severities.extend([sev]*(sev+1))
        random.shuffle(self.severities)
        super(ZenEventBenchDaemon, self).__init__(preferences, taskSplitter,
                                                configurationListener,
                                                initializationCallback,
                                                stoppingCallback)

    @defer.inlineCallbacks
    def load_devices(self):
        if not self.device_component_pairs:
            self.log.info("loading devices and components....")
            self.device_component_pairs = yield self.services.get('ZenPacks.zenoss.Benchmark.services.BenchmarkService').remoteMethod("getDeviceComponentPairs").__call__()
            self.log.info("Devices and components loaded")
            self.loading_devices = False
            self.last_reload = time.time()

    @defer.inlineCallbacks
    def load_event_classes(self):
        if not self.event_classes:
            self.event_classes = yield self.services.get('ZenPacks.zenoss.Benchmark.services.BenchmarkService').remoteMethod("getEventClasses").__call__()

    @defer.inlineCallbacks
    def publishLoop(self):
        if time.time() > self.last_reload + self.reload_devices_interval:
            self.device_component_pairs = None

        if not self.device_component_pairs and not self.loading_devices:
            self.loading_devices = True
            self.load_devices()
            self.load_event_classes() # we only read them once

        if self.device_component_pairs:
            yield self.publish()

        reactor.callLater(1.0/self.options.event_rate, self.publishLoop)

    @defer.inlineCallbacks
    def publish(self):
        """ """
        device = "localhost"
        component = ""
        event_class = "/Unknown"
        if self.device_component_pairs:
            device, component = random.choice(self.device_component_pairs)
        if self.event_classes:
            event_class = random.choice(self.event_classes)
        evt = dict(device=device, component=component, eventClass=event_class,
                   summary="Fake event {0}".format(time.time()), severity=random.choice(self.severities))
        yield self.sendEvent(evt)

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
            self.pushEventsLoop()
            self.log.debug('Calling connected.')
            self.connected()
            return result

        d.addCallback(callback)
        d.addErrback(twisted.python.log.err)
        reactor.run()
        if self._customexitcode:
            sys.exit(self._customexitcode)


if __name__ == '__main__':
    myPreferences = EventBenchPreferences()
    myTaskSplitter = NullTaskSplitter()
    daemon = ZenEventBenchDaemon(myPreferences, myTaskSplitter)
    daemon.run()
