##########################################################################################
# Creation, reading and manipulation of configuration files for schedconfig              #
#                                                                                        #
# Alden Stradling 10 Oct 2009                                                            #
# Alden.Stradling@cern.ch                                                                #
##########################################################################################

import sys

from controllerSettings import *
from miscUtils import *


# ----------------------------------------------------------------------#
# Config File Handling
# ----------------------------------------------------------------------
def buildDict(stdkeys):
    '''Build a copy of the queue dictionary from the configuration files. Standard key set can come in from the DB. '''

    if len(stdkeys) < 80 or type(stdkeys) is not list:
        print "No appropriate variables passed as standard keys. Exiting to prevent damage to the SVN."
        sys.exit()
    confd = {}
    # In executing files for variables, one has to put the variables in a contained, local context.
    locvars = {}
    base = os.getcwd()
    # Loop throught the clouds in the base folder
    try:
        clouds = os.listdir(configs)
    except OSError:
        # If the configs folder is missing and this is the first thing run,
        # Reload this from the DB.
        # When SVN is in place, this should be replaced by a svn checkout.
        # We choose element 0 to get the first result. This hack will go away.
        # configd = buildDict()
        # status = allMaker(configd)
        makeConfigs(sqlDictUnpacker(loadSchedConfig())[0])
        clouds = os.listdir(configs)
    if clouds.count(svn) > 0: clouds.remove(svn)

    for cloud in clouds:
        # Add each cloud to the dictionary
        confd[cloud] = {}
        # Loop throught the sites in the present cloud folder
        sites = os.listdir(configs + os.sep + cloud)
        for site in sites:
            # If this is the All file, create another entry.
            if site is All + postfix:
                # Get rid of the .py
                s = site[:-len(postfix)]
                # Run the file for the dictionaries
                fname = configs + os.sep + cloud + os.sep + site
                # The appropriate dictionaries are placed in locvars
                execfile(fname, {}, locvars)
                # Delete any keys that aren't in the DB
                for k in locvars[param].keys():
                    if k not in stdkeys: locvars[param].pop(k)
                for k in locvars[over].keys():
                    if k not in stdkeys: locvars[over].pop(k)
                # Locvars are then placed in the confd.
                confd[cloud][s][param] = locvars[param]
                confd[cloud][s][over] = locvars[over]
            # If the queue was misplaced, ignore it and mention it in the log:
            elif site.endswith(postfix):
                print '*** %s is not a site directory: this queue needs to be in a site. Ignoring.'
                continue
            # Add each site to the cloud
            confd[cloud][site] = {}
            # Loop throught the queues in the present site folders
            queues = [i for i in os.listdir(configs + os.sep + cloud + os.sep + site) if
                      i.endswith(postfix) and i is not svn]
            for q in queues:
                # Remove the '.py'
                queue = q[:-len(postfix)]
                # Add each queue to the site
                confd[cloud][site][queue] = {}
                if configReadDebug: print "Loaded %s %s %s" % (cloud, site, queue)
                # Run the file to extract the appropriate dictionaries
                # As a clarification, the Parameters, Override and Enabled variable are created when the config python file is executed
                fname = configs + os.sep + cloud + os.sep + site + os.sep + q
                # The appropriate dictionaries are placed in locvars
                execfile(fname, {}, locvars)
                # Delete any keys that aren't in the DB
                for k in locvars[param].keys():
                    if k not in stdkeys: locvars[param].pop(k)
                for k in locvars[over].keys():
                    if k not in stdkeys: locvars[over].pop(k)

                # Feed in the configuration
                confd[cloud][site][queue][param] = locvars[param]
                confd[cloud][site][queue][over] = locvars[over]
                try:
                    if queue != All:
                        confd[cloud][site][queue][enab] = locvars[enab]
                        confd[cloud][site][queue][param][dbkey] = queue
                    confd[cloud][site][queue][source] = dict(
                        [(key, 'Config') for key in locvars[param] if key not in excl and key in stdkeys])
                except KeyError:
                    print cloud, site, queue, param, key
                    pass

    # Now that we've seen all possible keys in stdkeys, make sure all queues have them:
    # No need to reload the cloud list...
    for cloud in clouds:
        # But the site list needs to be redone per cloud
        sites = os.listdir(configs + os.sep + cloud)
        for site in sites:
            # As does the queue list.
            # Loop throught the queues in the present site folders
            queues = [i for i in os.listdir(configs + os.sep + cloud + os.sep + site) if
                      i.endswith(postfix) and i is not svn and All not in i]
            for q in queues:
                # Remove the '.py'
                queue = q[:-len(postfix)]
                # Add each queue to the site
                try:
                    for key in (set(stdkeys) - set(excl)) - set(confd[cloud][site][queue][param]):
                        confd[cloud][site][queue][param][key] = None
                        if nonNull.has_key(key): confd[cloud][site][queue][param][key] = nonNull[key]
                    if confd[cloud][site][queue][param]['name'] == None: confd[cloud][site][queue][param][
                        'name'] = 'default'
                except KeyError:
                    pass

    # Leaving the All parameters unincorporated
    os.chdir(base)
    unicodeConvert(confd)
    return confd


def allMaker(configd, dbd):
    '''Extracts commonalities from sites for the All files.
    Returns 0 for success. Adds "All" queues to sites. Updates the
    provenance info in the input dictionary. '''
    all_d = {}
    dbcomp_d = {}

    # Presetting the All queue values from the Configs. These reign absolute -- to change individual queue
    # settings, an override or deletion of the parameter from the All.py file is necessary.

    # This is where we'll put all verified keys that are common across sites/clouds

    for cloud in [i for i in configd.keys() if (i is not All and i is not ndef)]:
        # Create a dictionary for each cloud
        all_d[cloud] = {}
        # For all regular sites:
        for site in [i for i in configd[cloud].keys() if (i is not All and i is not ndef)]:
            # Set up a site output dictionary
            all_d[cloud][site] = {}
            # Recreate the site comparison queue
            comp = {}
            # Loop over all the queues in the site, where the queue is not empty or "All"
            for queue in [i for i in configd[cloud][site].keys() if (i is not All and i is not ndef)]:
                # Create the key in the comparison dictionary for each parameter, if necessary, and assign a list that will hold the values from each queue
                if not len(comp):
                    comp = dict(
                        [(i, [configd[cloud][site][queue][param][i]]) for i in configd[cloud][site][queue][param].keys()
                         if i not in excl])
                else:
                    # Fill the lists with the values for the keys from this queue
                    for key in configd[cloud][site][queue][param]:
                        if key not in excl:
                            try:
                                comp[key].append(configd[cloud][site][queue][param][key])
                            except KeyError:
                                comp[key] = [configd[cloud][site][queue][param][key]]

            # Now, for the site, remove all duplicates in the lists.
            for key in comp:
                # If only one value is left, it is common to all queues in the site
                if len(reducer(comp[key])) == 1:
                    # So write it to the output for this cloud and site.
                    all_d[cloud][site][key] = reducer(comp[key])[0]

                # Running across sites to update source information in the main dictionary
                ## 	for cloud in [i for i in configd.keys() if i is not ndef]:
                ## 		for site in [i for i in configd[cloud].keys() if i is not ndef]:
                ## 			# No point in making an All file for one queue definition:
                ## 			if len(configd[cloud][site]) > 1:
                ## 				# Extract all affected keys for the site
                ## 				skeys = all_d[cloud][site].keys()
                ## 				# Going queue by queue, update the provenance for both cloud and site general parameters.
                ## 				for queue in [i for i in configd[cloud][site].keys() if (i is not All and i is not ndef)]:
                ## 					for key in skeys:
                ## 						configd[cloud][site][queue][source][key] = 'All.py: %s site' % site
                ## 				# Adding the "All" queue to the site
                ## 				if not configd[cloud][site].has_key(All):
                ## 					configd[cloud][site][All]={}
                ## 					configd[cloud][site][All][param] = all_d[cloud][site].copy()
                ## 				if not configd[cloud][site][All].has_key(over): configd[cloud][site][All][over] = {}

    ### Repeating much the same thing, but for the DB version.

    # This is where we'll put all verified keys that are common across sites/clouds
    for cloud in dbd.keys():
        # Create a dictionary for each cloud
        dbcomp_d[cloud] = {}
        # For all regular sites:
        for site in dbd[cloud].keys():
            # Set up a site output dictionary
            dbcomp_d[cloud][site] = {}
            # Recreate the site comparison queue
            dbcomp = {}
            # Loop over all the queues in the site
            for queue in dbd[cloud][site].keys():
                # Create the key in the comparison dictionary for each parameter, if necessary, and assign a list that will hold the values from each queue
                if not len(dbcomp):
                    dbcomp = dict(
                        [(i, [dbd[cloud][site][queue][param][i]]) for i in dbd[cloud][site][queue][param].keys() if
                         i not in excl])
                else:
                    # Fill the lists with the values for the keys from this queue
                    for key in dbd[cloud][site][queue][param]:
                        if key not in excl:
                            try:
                                dbcomp[key].append(dbd[cloud][site][queue][param][key])
                            except KeyError:
                                dbcomp[key] = [dbd[cloud][site][queue][param][key]]

            # Now, for the site, remove all duplicates in the lists.
            for key in dbcomp:
                # If only one value is left, it is common to all queues in the site
                if len(reducer(dbcomp[key])) == 1:
                    # So write it to the output for this cloud and site.
                    dbcomp_d[cloud][site][key] = reducer(dbcomp[key])[0]

    # Rolling through the sites, checking the DB common parameters to see if they match the All.py values in the queue
    # If the DB
    for cloud in dbcomp_d:
        for site in dbcomp_d[cloud]:
            # If there are common keys at all:
            keyDeleteList = []
            if len(dbcomp_d[cloud][site]):
                # If the cloud and site are in the config files and there exists an All.py file:
                if configd.has_key(cloud) and configd[cloud].has_key(site) and configd[cloud][site].has_key(All):
                    # Check each All key to see if the DB's
                    for key in configd[cloud][site][All][param]:
                        # This key is the same across the whole site in the DB
                        if dbcomp_d[cloud][site].has_key(key) and str(dbcomp_d[cloud][site][key]) == str(
                                configd[cloud][site][All][param][key]):
                            # If the key is consistent across a site in the DB, and it doesn't match the All.py file
                            # that means the All.py file has been modified, and it overrides the previous values in Config
                            if str(dbcomp_d[cloud][site][key]) != str(configd[cloud][site][All][param][key]):
                                for queue in configd[cloud][site]:
                                    configd[cloud][site][queue][param][key] = configd[cloud][site][All][param][key]
                        # If there is an All value and the DB lacks a consistent value and so do the queue entries, the queues need to be updated
                        # to avoid flip-flops
                        if not dbcomp_d[cloud][site].has_key(key) and not all_d[cloud][site].has_key(key) and \
                                configd[cloud][site][All][param].has_key(key):
                            for queue in configd[cloud][site]:
                                configd[cloud][site][queue][param][key] = configd[cloud][site][All][param][key]
                        # If there's an All.py value for this key, and the DB doesn't have a consistent value of that key
                        # for the site, then the All.py value needs to override as well
                        if not dbcomp_d[cloud][site].has_key(key) and all_d[cloud][site].has_key(key):
                            for queue in configd[cloud][site]:
                                configd[cloud][site][queue][param][key] = configd[cloud][site][All][param][key]
                        # If the DB has a consistent value for a site parameter, and it's the same as the All.py value, then it's already been set
                        # in a previous run and has been added to the All.py file at the same time. If there are changes in the individual queue
                        # values via the config files, they will be reflected in the *lack* of a generated All key. Therefore, the All file needs
                        # an edit to remove the redundant key.
                        if dbcomp_d[cloud][site].has_key(key) and not all_d[cloud][site].has_key(key):
                            keyDeleteList.append(key)
                    for key in keyDeleteList:
                        status = configd[cloud][site][All][param].pop(key)
    return 0


def composeFields(d, s, subdictname, primary_key, allFlag=0):
    ''' Populate a list for file writing that prints parameter dictionaries cleanly'''

    # "subdictname" is one of two things -- "Parameters" and "Override", depending on what part of the
    # file we're writing. They're defined generally as param and over. A third, JDL, applies only to jdllist imports
    # and replaces param

    # When writing one of the lesser tables, subdictname will just be the table name.

    keylist = d[subdictname].keys()
    try:
        # Remove the DB key and put in as the first parameter -- this will be "nickname", usually.
        keylist.remove(primary_key)
        keylist.sort()
    # keylist.insert(0, primary_key)

    # Unless it's not present -- then we'll just throw a warning.
    except ValueError:
        keylist.sort()
        # No point in warning for override or All dictionaries
        if subdictname == param and not allFlag:
            print 'DB key %s not present in this dictionary. Going to be hard to insert. %s' % (primary_key, str(d))

    # So we're writing a  "Parameters" or "Override" dictionary (subdictname)...
    s.append('%s = {' % subdictname + os.linesep)
    s_aside = []
    for key in keylist:
        if key not in excl:
            comment = ''
            value = str(d[subdictname][key])
            # Sanitize the inputs (having some trouble with quotes being the contents of a field):
            value = value.strip("'")
            if value == None: value = ''
            # For each key and value, check for multiline values, and add triple quotes when necessary
            if value.count(os.linesep):
                valsep = "'''"
            else:
                valsep = keysep
            s.append(spacing + keysep + key + keysep + dsep + valsep + value + valsep + pairsep + os.linesep)
    # Add in all the commented fields
    s.insert(0, '\n')
    s.extend(s_aside)
    # Complete the dictionary
    s.append(spacing + '}' + os.linesep)
    s.append(os.linesep)
    return 0


def makeConfigs(d):
    ''' Reconstitutes the configuration files from the passed dictionary'''
    # All outputs need to be re-encoded from unicode.
    unicodeEncode(d)
    for cloud in d:
        # The working cloud path is made from the config base
        cloudpath = configs + os.sep + cloud
        # Create the config path for each site
        for site in d[cloud]:
            # The working site path is made from the config base and cloud path
            path = cloudpath + os.sep + site
            # Try to make the path. If this fails, the path already exists.
            try:
                os.makedirs(path)
            except OSError:
                if configWriteDebug:
                    print 'Failed to make path ', path
                    os.listdir(cloudpath)
            # Go on in...
            os.chdir(path)
            # And for each queue, create a config file.
            for queue in d[cloud][site]:
                buildFile(queue, d[cloud][site][queue])
    return


def buildFile(name, d):
    '''Consolidate the composition and writing of the files'''
    startstr = '''
# This dictionary contains the parameters for one queue.
'''
    overridestr = '''
'''

    switchstr = 'Enabled = '
    # Load up the file intro
    s = [startstr]
    # Put the queue on/off switch in place if not an All file
    if name == All:
        allFlag = 1
    else:
        allFlag = 0
    # All queues are enabled by default, because they came from AGIS
    s.append(switchstr + 'True' + '\n\n')
    # I'm taking advantage of the universality of lists.
    # composeFields is modifying the list itself rather than a copy.
    # Since the params in the All files have no keys to find, we warn
    # the composeFields code.
    composeFields(d, s, param, dbkey, allFlag)
    # No more overrides or other text.
    f = file(name + postfix, 'w')
    f.writelines(s)
    f.close()
