"""Support for cz_pub_tran domain
The async_update connections checks all connections every minute
If the connection is scheduled, it skips the update. 
But every 5 minutes it updates all connections regardless - to check on delay
"""
from czpubtran.api import czpubtran
import logging
from homeassistant.helpers import config_validation as cv, discovery
from datetime import datetime, date, time, timedelta
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
    CONF_SENSORS,
    CONF_NAME
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import asyncio
from homeassistant.helpers.event import async_call_later
from .sensor import (
    DOMAIN,
    CONF_USERID,
    DEFAULT_SCAN_INTERVAL,
    CONF_FORCE_REFRESH_INTERVAL,
    CONF_DETAIL_FORMAT,
    CONFIG_SCHEMA,
    COMPONENT_NAME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass, config):
    """Setup the cz_pub_tran platform."""
    conf = CONFIG_SCHEMA(config).get(DOMAIN)
    user_id = conf.get(CONF_USERID)
    scan_interval = conf.get(CONF_SCAN_INTERVAL).total_seconds()
    force_refresh_interval = conf.get(CONF_FORCE_REFRESH_INTERVAL)
    detail_format=conf.get(CONF_DETAIL_FORMAT)
    session = async_get_clientsession(hass)
    hass.data[DOMAIN]= ConnectionPlatform(hass,user_id,scan_interval,force_refresh_interval,detail_format,session)
    hass.helpers.discovery.load_platform(COMPONENT_NAME,DOMAIN, conf[CONF_SENSORS], config)
    async_call_later(hass,1, hass.data[DOMAIN].async_update_Connections())
    return True

class ConnectionPlatform():
    def __init__(self,hass,user_id,scan_interval,force_refresh_interval,detail_format,session):
        self._hass = hass
        self._user_id = user_id
        self._scan_interval = scan_interval
        self._force_refresh_interval = force_refresh_interval
        self._detail_format = detail_format
        self._entity_ids = []
        self._connections = []
        self._api = czpubtran(session,user_id)

    def add_sensor(self,sensor):
        self._connections.append(sensor)

    def entity_ids(self):
        return self._entity_ids

    def add_entity_id(self,id):
        self._entity_ids.append(id)

    async def async_update_Connections(self):
        for entity in self._connections:
            if entity.scheduled_connection(self._force_refresh_interval):
                _LOGGER.debug( f'({entity._name}) departure already scheduled for {entity._departure} - not checking connections')
                continue
            await self._api.async_find_connection(entity._origin,entity._destination,entity._combination_id)
            if self._detail_format=='list':
                connections_long=self._api.connections
                # departure,duration,state,connections,description,delay
                entity.update_status(self._api.departure,self._api.duration,f'{self._api.departure} ({self._api.line})','',connections_long,'')
            else:
                if self._detail_format=='HTML':
                    connections_long='<table>\n<tr><th>Line</th><th>Departure</th><th>From</th><th>Arrival</th><th>To</th><th>Delay</th></tr>'
                else:
                    connections_long=''
                connections_short=''
                delay=''
                long_delim=''
                for trains in self._api.connections:
                    line=trains['line']
                    depTime=trains['depTime']
                    depStation=trains['depStation']
                    arrTime=trains['arrTime']
                    arrStation=trains['arrStation']
                    if long_delim=='':
                        connections_short=line
                    else:
                        connections_short=connections_short+"-"+depStation.replace(" (PZ)","")+"-"+line
                    if trains['delay'] != '':
                        if self._detail_format=='HTML':
                            connections_long=connections_long+f'<tr><td>{line}</td><td>{depTime}</td><td>{depStation}</td><td>{arrTime}</td><td>{arrStation}</td><td>{trains["delay"]}min</td></tr>\n'
                        else:
                            connections_long=connections_long+long_delim+f'{line:<4} {depTime:<5} ({depStation}) -> {arrTime:<5} ({arrStation})   !!! {trains["delay"]}min delayed'
                        if delay=='':
                            delay = f'line {line} - {trains["delay"]}min delay'
                        else:
                            delay = delay + f' | line {line} - {trains["delay"]}min delay'
                    else:
                        if self._detail_format=='HTML':
                            connections_long=connections_long+f'<tr><td>{line}</td><td>{depTime}</td><td>{depStation}</td><td>{arrTime}</td><td>{arrStation}</td><td></td></tr>\n'
                        else:
                            connections_long=connections_long+long_delim+f'{line:<4} {depTime:<5} ({depStation}) -> {arrTime:<5} ({arrStation})'
                    long_delim='\n'
                if self._detail_format=='HTML':
                    connections_long=connections_long+'</table>'
                entity.update_status(self._api.departure,self._api.duration,self._api.departure+" ("+connections_short+")",connections_short,connections_long,delay)
        async_call_later(self._hass, self._scan_interval, self.async_update_Connections())
