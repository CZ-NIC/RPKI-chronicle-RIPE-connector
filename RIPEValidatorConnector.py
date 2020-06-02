#!/usr/bin/env python3
# coding: utf-8

"""
RIPEValidatoConnector

Copyright (C) 2020 CZ.NIC, z.s.p.o.

This module is part of RPKI-chronicle project -- web-based history keeper for
RPKI and BGP.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import requests
import json
import re
import ipaddress

warn = False
def _warn(text):
    if warn:
        print(text, file=sys.stderr)


class RPKIValidatorAPIException(Exception):
    """ Generic class for reporting errors in interaction with the RIPE NCC RPKI Validator.
    """
    pass


class RPKIValidatorAPI(object):
    """ This object is an entry point to connector that use API of the
    independently running RIPE NCC RPKI validator
    (https://www.ripe.net/manage-ips-and-asns/resource-management/certification/tools-and-resources).
    The Validator exposes API described in
    https://www.ripe.net/support/documentation/developer-documentation/rpki-validator-api/rpki-validator-api
    and there are internal API pieces as of RPKI validator version 765874eabf3e08edc1b9e026d389b73b0442f397
    that allows to obtain BGP preview data for further processing.
    """

    RIPE_VALIDATOR_URL = r'https://rpki-validator.ripe.net/'
    EXPORT_JSON_API_URI = r'api/export.json'
    BGP_PREVIEW_API_URI = r'api/bgp/'

    JSON_KEY_META = r'metadata'
    JSON_KEY_TOTALCOUNT = r'totalCount'
    JSON_KEY_LASTMODIFIED = r'lastModified'
    JSON_KEY_DATA = r'data'

    JSON_KEY_ASN = r'asn'
    JSON_KEY_PREFIX = r'prefix'
    JSON_KEY_VALIDITY = r'validity'

    asnre = re.compile(r'^AS([0-9]+)$')

    JSON_DATA_UNKNOWN = r'UNKNOWN'
    JSON_DATA_VALID = r'VALID'
    JSON_DATA_INVALID_ASN = r'INVALID_ASN'
    JSON_DATA_INVALID_LENGTH = r'INVALID_LENGTH'

    MAX_REQUEST_ATTEMPTS = 3

    RPKI_UNKNOWN = 0
    RPKI_VALID = 1
    RPKI_INVALID_ASN = 2
    RPKI_INVALID_LENGTH = 3

    def __init__(self, urlBase=None):
        """ urlBase - access point to the RIPE validator, i.e. https://rpki-validator.ripe.net/
        """
        if urlBase:
            self.urlBase = urlBase
        else:
            self.urlBase = self.RIPE_VALIDATOR_URL

    @classmethod
    def _get(cls, url):
        """ query the API on a specific URL
        - url - the URL to query with get request
        returns: decoded json in pythonic form
        """
        r = requests.get(url, stream=True)
        _warn("GET %s" % url)
        _warn("Response: %s" % str(r.content))
        return json.loads(r.content)
    
    def getROAs(self):
        """ request the validator for current list of ROAs
        returns: pythonic form of json response
        the format of resposne: TODO
        """
        url = self.urlBase + self.EXPORT_JSON_API_URI
        return self._get(url)

    def _genBGPPreviewUrl(self, startFrom=1, pageSize=1):
        """ internal: generate URL for BGPPreview API of the validator
        int starFrom - the first record in the result set
        int pageSize - number of records to return
        returns URL for the _get method
        """
        return '%s%s?startFrom=%d&pageSize=%d' % (self.urlBase, self.BGP_PREVIEW_API_URI, startFrom, pageSize)

    @classmethod
    def decodeBGPPreviewMeta(cls, response):
        """ decode metadata from the validator and return them pythonic form
        returns (int totalCount, int lastModified), lastModified is timestamp
        """
        return (int(response[cls.JSON_KEY_META][cls.JSON_KEY_TOTALCOUNT]),
                int(int(response[cls.JSON_KEY_META][cls.JSON_KEY_LASTMODIFIED])/1000))

    @classmethod
    def extractBGPPreviewData(cls, response):
        """ extracts data list from the JSON response
        returns list(dict(row repsesented in JSON))
        """
        return response[cls.JSON_KEY_DATA]

    @classmethod
    def decodeBGPPrevRow(cls, row):
        """ decode JSON data row represented in dict generated from JSON, i.e.
        {'asn': 'AS208328', 'prefix': '2a0e:b107:1c2::/48', 'validity': 'INVALID_LENGTH'}
        returns (int(208328), ipaddress.ip_network('2a0e:b107:1c2::/48'), RPKIValidatorAPI.INVALID_LENGTH)
        """

        asntxt = row[cls.JSON_KEY_ASN]
        m = cls.asnre.match(asntxt)
        if m:
            asn = int(m.group(1))
        else:
            raise RPKIValidatorAPIException("Can not decode ASN: %s" % str(row[cls.JSON_KEY_ASN]))

        pfx = ipaddress.ip_network(row[cls.JSON_KEY_PREFIX])

        if row[cls.JSON_KEY_VALIDITY] == cls.JSON_DATA_UNKNOWN:
            val = cls.RPKI_UNKNOWN
        elif row[cls.JSON_KEY_VALIDITY] == cls.JSON_DATA_VALID:
            val = cls.RPKI_VALID
        elif row[cls.JSON_KEY_VALIDITY] == cls.JSON_DATA_INVALID_ASN:
            val = cls.RPKI_INVALID_ASN
        elif row[cls.JSON_KEY_VALIDITY] == cls.JSON_DATA_INVALID_LENGTH:
            val = cls.RPKI_INVALID_LENGTH
        else:
            raise RPKIValidatorAPIException("Unknown validity: %s" % str(row[cls.JSON_KEY_VALIDITY]))

        return (asn, pfx, val)
        

    def getBGPPreviewMeta(self):
        """ request metadata from the validator and return them pythonic form
        returns (int totalCount, int lastModified), lastModified is timestamp
        """
        response = self._get(self._genBGPPreviewUrl(1,1))
        return self.decodeBGPPreviewMeta(response)

    def getBGPPreviewLastModified(self):
        """ get timestamp of the BGP Preview data last modification in the validator
        """
        totalCount, lastModified = self.getBGPPreviewMeta()
        return lastModified

    def getBGPPreview(self, maxAttempts=MAX_REQUEST_ATTEMPTS):
        """ execute up to maxAttempts GET requests to the BGP preview API endpoint
        returns pythonic version of the json response if it is downloaded in one piece
        and consistently with pre-requested metadata
        raise exception if the 
        """
        for i in range(0, self.MAX_REQUEST_ATTEMPTS):
            totalCount, lastModified = self.getBGPPreviewMeta()
            response = self._get(self._genBGPPreviewUrl(0, totalCount))
            #response = self._get(self._genBGPPreviewUrl(1, 1000))
            dataTotalCount, dataLastModified = self.decodeBGPPreviewMeta(response)
            if lastModified != dataLastModified:
                _warn("Warn: lastModified != dataLastModified")
                continue
            if totalCount != dataTotalCount:
                _warn("Warn: totalCount != dataTotalCount")
                continue
            if len(response[self.JSON_KEY_DATA]) != totalCount:
                _warn("Warn: len() %d != totalCount %d" % (len(response[self.JSON_KEY_DATA]), totalCount))
                continue

            return response

        raise RPKIValidatorAPIException("Failed to download BGP Preview from %s on %d attempts"
                % (self.urlBase, maxAttempts))




def main():
    """ Test the RPKIValidatorAPI class """
    apiep = RPKIValidatorAPI()
    print( 'ROAs: %s' % str(apiep.getROAs()) )
    print( 'BGP preview totalCount=%d, lastModified=%d' % apiep.getBGPPreviewMeta() )
    print( 'BGP preview data: %s' % str(apiep.getBGPPreview()) )



if __name__ == '__main__':
    main()

