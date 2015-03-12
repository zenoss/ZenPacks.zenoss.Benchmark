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

here = lambda *x: os.path.join(os.path.dirname(__file__), *x)

unused(Globals, DeviceProxy)

COLLECTOR_NAME = 'zenmodelerbench'
log = logging.getLogger("zen.%s" % COLLECTOR_NAME)


maps = []

for fname in os.walk(here('data')).next()[2]:
    with open(here('data', fname)) as f:
        maps.extend(cPickle.load(f))


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
        return

    def buildOptions(self, parser):
        """
        Command-line options to be supported
        """
        parser.add_option('--stats', dest='stats',
                          action='store_true', default=False,
                          help='Print statistics to log every 2 secs')

        parser.add_option('--datamapdir', dest='datamapdir',
                          default='.',
                          help='Directory containing datamaps')

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


def random_id():
    return md5.md5(os.urandom(20)).hexdigest()[:10]


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

    @defer.inlineCallbacks
    def publishLoop(self):
        reactor.callLater(self.options.datamaprate, self.publishLoop)
        yield self.publish()

    def config(self):
        return self.services.get('DiscoverService')

    @defer.inlineCallbacks
    def publish(self):
        result = yield self.config().callRemote("createDevice", random_ip(),
                    deviceName=random_id(), devicePath="/Network/Cisco")
        if isinstance(result, Failure):
            self.log.exception("Unable to create device")
            return
        dev, created = result
        id_ = dev.getId()
        x = yield self.config().callRemote("applyDataMaps", id_, maps)
        print x
        if x:
            self.log.info("CHANGES TO DEVICE MADE")


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
