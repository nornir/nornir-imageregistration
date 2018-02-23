'''
Created on May 21, 2013

@author: u0490822
'''

import argparse
import logging
import os
import sys

import nornir_imageregistration.assemble

import nornir_shared.misc


def __CreateArgParser(ExecArgs=None):



    # conflict_handler = 'resolve' replaces old arguments with new if both use the same option flag
    parser = argparse.ArgumentParser(description="Produce a registered image for the moving image in a .stos file")

    parser.add_argument('-input', '-i',
                        action='store',
                        required=True,
                        type=str,
                        help='Input .mosaic file path',
                        dest='inputpath')

    parser.add_argument('-output', '-o',
                        action='store',
                        required=True,
                        type=str,
                        help='Output mosaic file path',
                        dest='outputpath')

    parser.add_argument('-tilepath', '-s',
                        action='store',
                        required=False,
                        type=float,
                        default=1.0,
                        help='Path to directory containing tiles listed in mosaic',
                        dest='tilepath'
                        )

    return parser

def ParseArgs(ExecArgs=None):
    if ExecArgs is None:
        ExecArgs = sys.argv

    parser = __CreateArgParser()

    return parser.parse_known_args(args=ExecArgs)


def OnUseError(message):
    parser = __CreateArgParser()
    parser.print_usage()

    log = logging.getLogger('nornir-assemble')
    log.error(message)

    sys.exit()

def ValidateArgs(Args):
    if not os.path.exists(Args.inputpath):
        OnUseError("Input mosaic file not found: " + Args.inputpath)
        
    if Args.tilepath is None:
        Args.tilepath = os.path.dirname(Args.inputpath)
        

    if not os.path.exists(os.path.dirname(Args.outputpath)):
        os.makedirs(os.path.dirname(Args.outputpath))

    if not Args.tilepath is None:
        if not os.path.exists(Args.tilepath):
            OnUseError("Tile path not found: " + Args.tilepath)
            
    if not '.' in Args.outputpath:
        Args.outputpath = Args.outputpath + '.mosaic'

def Execute(ExecArgs=None):
    if ExecArgs is None:
        ExecArgs = sys.argv[1:]
        
    (Args, extra) = ParseArgs(ExecArgs)

    ValidateArgs(Args)
 
    mosaic = Mosaic.LoadFromMosaicFile(Args.inputpath) 

 
    timer = TaskTimer()
    timer.Start("ArrangeTiles " + TilesDir)
    translated_mosaic = mosaic.ArrangeTilesWithTranslate(Args.tilepath, usecluster=False)
    timer.End("ArrangeTiles " + TilesDir, True)
    translated_mosaic.SaveToMosaicFile(OutputDir)
   
    if os.path.exists(Args.outputpath):
        print("Wrote: " + Args.outputpath)
    else:
        print("Outputfile is missing, unknown error: " + Args.outputpath)
     
         

if __name__ == '__main__':

    nornir_shared.misc.SetupLogging(os.path.join(os.path.dirname(args.outputpath), "Logs"))

    Execute()
