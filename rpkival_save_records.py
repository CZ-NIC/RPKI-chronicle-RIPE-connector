#!/usr/bin/env python3
# coding: utf-8

"""
rpkival_save_records script

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
import re
import datetime
from collections import defaultdict
import ipaddress
import time
import fasteners
from sqlalchemy import desc, update

import model
import RIPEValidatorConnector


LOCKFILE = '/run/rpkichronicle/rpkival_save_rec.lock'





def w(text):
    """ Print warning/debugging text
    """
    print(text, file=sys.stderr)


def getLastUpdate(sess):
    """ Query DB for the last timestamp in stats table. It is effectively time of
    the last update.

    sess - SQLAlchemy session
    """
    sts = sess.query(model.Statistic).order_by(desc(model.Statistic.ts)).first()
    if sts:
        return sts.ts
    else:
        return datetime.datetime.min


def makeRecord(sess, asn, pfx, val, ts):
    """ Make record for a new conflicts if it is not yet in DB
    sess - SQLAlchemy session
    asn - int
    pfx - str or ipaddress.ip_network()
    val - int(status) numerical value for the conflict defined in RPKIValidatorAPI class
    ts - datetime timestamp
    """
    po = sess.query(model.PrefixAsn).filter(model.PrefixAsn.asn == asn, model.PrefixAsn.prefix == str(pfx)).one_or_none()

    if not po:
        po = model.PrefixAsn()
        po.asn = asn
        po.prefix = str(pfx)
        sess.add(po)
        #w("New prefix-origin %s AS%d" % (str(pfx), asn))

    conf = sess.query(model.Conflict).filter(model.Conflict.prefix_asn_id == po.id, model.Conflict.end == None, model.Conflict.status == val).one_or_none()
    if not conf:
        conf = model.Conflict()
        conf.prefix_asn_id = po.id
        conf.status = val
        conf.start = ts
        conf.end = None
        sess.add(conf)
        #w("New conflict %s AS%d val %d" % (str(po.prefix), po.asn, val))


def closeRecords(sess, currentConflicts, ts):
    """ Close records in DB that are not present in currentConflicts anymore.
    sess - SQLAlchemy session
    currentConflicts - {(int(asn), ipaddress.ip_network(pfx)):status}, status is numerical value for
    the conflict defined in RPKIValidatorAPI class
    ts - datetime timestamp
    """
    openconfs = sess.query(model.Conflict).join(model.PrefixAsn).filter(model.Conflict.end == None)
    for oc in list(openconfs):
        k = (oc.prefix_asn.asn, ipaddress.ip_network(oc.prefix_asn.prefix))
        if k in currentConflicts and currentConflicts[k] == oc.status:
            pass
            #w("Running conflict %s AS%d" % (str(oc.prefix_asn.prefix), oc.prefix_asn.asn))
        else:
            sess.query(model.Conflict).filter(model.Conflict.prefix_asn_id == oc.prefix_asn_id, model.Conflict.start == oc.start, model.Conflict.end == None).update({model.Conflict.end: ts})
            #w("Conflict finished %s AS%d" % (str(oc.prefix_asn.prefix), oc.prefix_asn.asn))


def updateRPKIRecords(sess, conflicts, ts):
    """ Update conflicting RPKI records
    First close disappeared or changed records.
    Then create new records for new conglicts.
    """
    closeRecords(sess, conflicts, ts)

    for asn, pfx in conflicts:
        makeRecord(sess, asn, pfx, conflicts[(asn,pfx)], ts)



def appendCurrentStats(sess, stats, ts):
    """ Append statistic in stats dict to DB.
    sess - SQLAlchemy session
    stats - {0:num_unknown, 1:num_valid, 2:num_inval_asn, 3:num_inval_pfxlen}
    ts - datetime timestamp
    """
    s = model.Statistic()
    s.ts = ts
    s.unknown = stats[RIPEValidatorConnector.RPKIValidatorAPI.RPKI_UNKNOWN]
    s.valid = stats[RIPEValidatorConnector.RPKIValidatorAPI.RPKI_VALID]
    s.invalid_asn = stats[RIPEValidatorConnector.RPKIValidatorAPI.RPKI_INVALID_ASN]
    s.invalid_pfxlen = stats[RIPEValidatorConnector.RPKIValidatorAPI.RPKI_INVALID_LENGTH]
    sess.add(s)


def doUpdates():
    """ Function of the script to be ran every 30 minutes or every hour under
    lock protection.

    Open connection to the validator and obtain data.
    Count stats and run updates to the DB.
    """

    # open RIPE validator connection
    apiep = RIPEValidatorConnector.RPKIValidatorAPI()

    # get current metadata
    bgpprev = apiep.getBGPPreview()
    totalCount, lastModified = apiep.decodeBGPPreviewMeta(bgpprev)

    # get current time
    currTime = int(time.time())
    ts = datetime.datetime.fromtimestamp(currTime)
    w("Running update at %s (%d)" % (str(ts), currTime))

    # test if metadata makes sense
    if lastModified > currTime:
        raise Exception("Validator returned last modified time in future: %d" % lastModified)

    w("Validator returned: lastModified=%d (%s) totalCount=%d" % (lastModified, str(datetime.datetime.fromtimestamp(lastModified)), totalCount))

    # open DB connection
    sess = model.Session()

    # test if date point is linear in time
    if ts > getLastUpdate(sess):
        stats = defaultdict(lambda: 0)
        conflicts = {}

        # extract data from validator response
        data = apiep.extractBGPPreviewData(bgpprev)
        for dr in data:
            asn, pfx, val = apiep.decodeBGPPrevRow(dr)
            stats[val]+=1
            if val >= RIPEValidatorConnector.RPKIValidatorAPI.RPKI_INVALID_ASN:
                conflicts[(asn,pfx)] = val

        # update conflict records
        updateRPKIRecords(sess, conflicts, ts)
        # update stats
        appendCurrentStats(sess, stats, ts)

        # finish
        sess.commit()
        sess.close()
    else:
        w("DB last datapoint in future. Skipping datapoint.")
        sess.close()

    endTime = time.time()
    w("Finished update at %s (%d)" % (str(datetime.datetime.fromtimestamp(endTime)), endTime))


def main():
    """ Main function of the script to be ran every 30 minutes or every hour.

    Main function takes no parameters since this is fire&forget type of script.
    This script needs a lock which is statically determined by a global variable
    LOCKFILE.
    """
    lock = fasteners.InterProcessLock(LOCKFILE)
    if lock.acquire(blocking=False):
        doUpdates()
    else:
        print("Can not acquire lock %s. Exit." % LOCKFILE)
        return -1


if __name__ == '__main__':
    main()
