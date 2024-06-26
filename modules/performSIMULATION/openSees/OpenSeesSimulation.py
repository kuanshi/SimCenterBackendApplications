#!/usr/bin/env python3

import sys
import os
import subprocess
#from pathlib import Path

def main(args):

    # set filenames
    aimName = args[1]
    samName = args[3]
    evtName = args[5]
    edpName = args[7]
    simName = args[9]

    # remove path to AIM file, so recorders are not messed up
    #      .. AIM file ro be read is in current dir (copy elsewhere)
    aimName = os.path.basename(aimName)
    scriptDir = os.path.dirname(os.path.realpath(__file__))

    # aimName = Path(args[1]).name
    # scriptDir = Path(__file__).resolve().parent

    #If requesting random variables run getUncertainty
    #Otherwise, Run Opensees 
    if "--getRV" in args:
        getUncertaintyCommand = '"{}/OpenSeesPreprocessor" {} {} {} {}'.format(scriptDir, aimName, samName, evtName, simName)
        exit_code = subprocess.Popen(getUncertaintyCommand, shell=True).wait()
        #exit_code = subprocess.run(getUncertaintyCommand, shell=True).returncode
        #if not exit_code==0:
        #    exit(exit_code)
    else:
        #Run preprocessor
        preprocessorCommand = '"{}/OpenSeesPreprocessor" {} {} {} {} {} example.tcl'.format(scriptDir, aimName, samName, evtName, edpName, simName)
        exit_code = subprocess.Popen(preprocessorCommand, shell=True).wait()   
        # exit_code = subprocess.run(preprocessorCommand, shell=True).returncode # Maybe better for compatibility - jb
        #if not exit_code==0:
        #    exit(exit_code)

        #Run OpenSees
        exit_code = subprocess.Popen("OpenSees example.tcl >> workflow.err 2>&1", shell=True).wait()
        # Maybe better for compatibility, need to doublecheck - jb
        #exit_code = subprocess.run("OpenSees example.tcl >> workflow.err 2>&1", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode 
        
        #if os.path.isfile("./workflow.err"):
        #    with open("./workflow.err", 'r') as file:   
        #        lines = file.readlines()
        #        # Iterate through each line
        #        for line in lines:
        #            # Check if the keyword exists in the line
        #            if "error" in line.lower():
        #                exit_code = -1
        #                exit(exit_code)

        #Run postprocessor
        postprocessorCommand = '"{}/OpenSeesPostprocessor" {} {} {} {}'.format(scriptDir, aimName, samName, evtName, edpName)
        exit_code = subprocess.Popen(postprocessorCommand, shell=True).wait()
        # exit_code = subprocess.run(postprocessorCommand, shell=True).returncode # Maybe better for compatibility - jb
        # if not exit_code==0:
        #     exit(exit_code)


if __name__ == '__main__':

    main(sys.argv[1:])
