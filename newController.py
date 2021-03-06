#! /usr/bin/env python
#######################################################
# Handles storage and modification of queue data      #
# in the ATLAS PanDA schedconfig table                #
# for ATLAS production and analysis queues.           #
#                                                     #
# Alden Stradling (Alden.Stradling@cern.ch) 23 Jun 09 #
#######################################################

# TODO:

# This code has been organized for easy transition into a class structure.

from backupHandling import *
from configFileHandling import *
from dictHandling import *
from multicloudHandling import *
from networkHandling import *
from swHandling import *


def loadConfigs():
    '''Run the schedconfig table updates'''
    # Load the database as it stands as a primary reference
    dbd, database_queue_keys = sqlDictUnpacker(loadSchedConfig())

    standard_keys = list(keyCensus(collapseDict(dbd)))

    agisd = agisDictUnpacker(standard_keys)
    # Compose the "All" queues for each site
    status = allMaker(agisd, dbd)
    # Make sure all nicknames are kosher
    nicknameChecker(agisd)
    nicknameChecker(dbd)

    # Compare the DB to the present built configuration to find the queues that are changed.
    up_d, del_d = compareQueues(collapseDict(dbd), collapseDict(agisd))

    # Get the database updates prepared for insertion.
    # The Delete list is just a list of SQL commands (don't add semicolons!)
    del_l = buildDeleteList(del_d, 'schedconfig')
    # The other updates are done using the standard replaceDB method from the SchedulerUtils package.
    # The structure of the list is a list of dictionaries containing column/value as the key/value pairs.
    # The primary key is specified for the replaceDB method. For schedconfig, it's dbkey.
    # (specified in controllerSettings
    up_l = buildUpdateList(up_d, param, dbkey)

    # Information regarding
    if len(del_d): emailDeletions('%s' % ', '.join(del_d.keys()))
    if float(len(del_d)) / float(len(collapseDict(agisd))) >= float(maxDeletedQueuePercentage) / 100:
        msg = 'Deleting too many queues: %d percent is higher than the maximum allowed of %d percent' % (
        int(float(len(del_d)) / float(len(collapseDict(agisd))) * 100), maxDeletedQueuePercentage)
        emailDeletionWarning(msg)
        print msg
        if genDebug:
            return dbd, agisd, up_d, del_d, del_l, up_l, [], [], []
        else:
            return 1

    # If the safety is off, the DB update can continue
    if safety is not 'on':
        utils.initDB()
        unicodeEncode(del_l)
        # Individual SQL statements to delete queues that need deleted
        if not delDebug:
            print '\n\n Queues Being Deleted:\n'
            for i in sorted(del_d): print del_d[i][dbkey], del_d[i]['cloud']
            print
            for i in del_l:
                try:
                    print i
                    status = utils.dictcursor().execute(i)

                except:
                    print 'Failed SQL Statement: ', i
                    print status
                    print sys.exc_info()

        # Schedconfig table gets updated all at once
        print 'Updating SchedConfig'

        # Since all inputs are unicode converted, all outputs need to be encoded.
        print '\n\n Queues Being Updated or Added:\n'
        for i in sorted(up_d): print up_d[i][dbkey], up_d[i]['cloud']
        print
        unicodeEncode(up_l)

        #### Here's the main update.
        status = utils.replaceDB('schedconfig', up_l, key=dbkey)

        # Error Reporting and recovery
        status = status.split('<br>')
        if len(status) < len(up_l):
            # If we have to go queue-by-queue, here's how it's done.
            print 'Bulk Update Failed. Retrying queue-by-queue.'
            status = []
            errors = []
            for up in up_l:
                print up[dbkey]
                # Going with each key.
                status.append(utils.replaceDB('schedconfig', [up], key=dbkey))
                if 'Error' in status[-1]:
                    errors.append(status[-1] + str(up))
            errors = [stat for stat in status if 'Error' in stat]
            f = file(errorFile, 'w')
            f.write(str(errors))
            f.close()
            shortErrors = [')</b></font>' + err.split(')</b></font>')[1] for err in errors]
            if not genDebug: emailError(str(shortErrors))

        # Changes committed after all is successful, to avoid partial updates
        utils.commit()
        utils.endDB()

    # Check out the db as a new dictionary
    newdb, sk = sqlDictUnpacker(loadSchedConfig())
    # If the checks pass (no difference between the DB and the new configuration)
    checkUp, checkDel = compareQueues(collapseDict(newdb), collapseDict(agisd))
    if len(del_d) or len(up_d):
        # Make the necessary changes to the configuration files
        backupCreate(newdb)

    # For development purposes, we can get all the important variables out of the function. Usually off.
    if genDebug:
        return dbd, agisd, up_d, del_d, del_l, up_l, newdb, checkUp, checkDel
    else:
        return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    # A better argument parser will be needed in the future
    if '--safety' in args:
        print 'Safety is ON! No writes to the DB.'
        safety = 'on'
    if '--debug' in args: genDebug = True
    if '--sw' in args: runSW = True
    if '--network' in args: network = True
    if '--multicloud' in args: multicloud = True
    keydict = {}

    # Running in schedconfig update mode.
    if not runSW and not network and not multicloud:
        print "\n\n                    *** Running Schedconfig Update ***\n\n"
        # Backup of all the volatile DB paramaters before the operation
        volatileBackupCreate()
        if not genDebug:
            try:
                # All of the passed dictionaries will be eliminated at the end of debugging. Necessary for now.
                dbd, database_queue_keys = sqlDictUnpacker(loadSchedConfig())
                status = loadConfigs()
            except:
                emailError(sys.exc_value)
        else:
            l = []
            # All of the passed dictionaries will be eliminated at the end of debugging. Necessary for now.
            dbd, database_queue_keys = sqlDictUnpacker(loadSchedConfig())
            dbd, agisd, up_d, del_d, del_l, up_l, newdb, checkUp, checkDel = loadConfigs()

    # Running in SW mode
    if runSW:
        print "\n\n                    *** Running Installed SW Update ***\n\n"
        dbd, database_queue_keys = sqlDictUnpacker(loadSchedConfig())
        if genDebug:
            print 'Received debug info'
            sw_db, sw_agis, deleteList, addList, sw_union = updateInstalledSW(collapseDict(dbd))
        else:
            updateInstalledSW(collapseDict(dbd))

    # Running in network matrix update mode
    if network:
        print "\n\n                    *** Running Network Matrix Update ***\n\n"
        nc = networkHandling()
        nc.Proceed()

    # Running in multicloud update mode
    if multicloud:
        print "\n\n                    *** Running Multicloud Update ***\n\n"
        mc = multicloudHandling()
        mc.Proceed()
