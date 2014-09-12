'''
Created on Jun 26, 2012

@author: James Anderson
'''

from collections import deque
import logging
import multiprocessing
import os
import subprocess

import numpy
from pylab import median, mean, std, sqrt, imread, ceil, floor, mod
import scipy.ndimage.measurements
import scipy.stats

import nornir_pools as pools
import nornir_shared.histogram
import nornir_shared.images as images
import nornir_shared.prettyoutput as PrettyOutput

from . import core
from . import im_histogram_parser


class ImageStats():

    @property
    def median(self):
        return self._median

    @property
    def mean(self):
        return self._mean

    @property
    def stddev(self):
        return self._stddev

    def __init__(self):
        self._median = None
        self._mean = None
        self._stddev = None

    @classmethod
    def Create(cls, Image):
        '''Returns an object with the mean,median,std.dev of an image,
           this object is attached to the image object and only calculated once'''

        if '__IrtoolsImageStats__' in Image.__dict__:
            return Image.__dict__["__IrtoolsImageStats__"]

        istats = ImageStats()

        istats._median = median(Image)
        istats._mean = mean(Image)
        istats._stddev = std(Image)

        Image.__dict__["__IrtoolsImageStats__"] = istats
        return istats


def Prune(filenames, MaxOverlap=None):

    if isinstance(filenames, str):
        listfilenames = [filenames];
    else:
        listfilenames = filenames;

    # logger = logging.getLogger('irtools.prune');

    if MaxOverlap is None:
        MaxOverlap = 0;

    assert isinstance(listfilenames, list);

    FilenameToResult = __InvokeFunctionOnImageList__(listfilenames, Function=__PruneFileSciPy__, MaxOverlap=MaxOverlap);

    # Convert results to a float
    for k in FilenameToResult:
        FilenameToResult[k] = float(FilenameToResult[k][1]);

    if isinstance(filenames, str):
        return list(FilenameToResult.items())[0];
    else:
        return FilenameToResult;

def __InvokeFunctionOnImageList__(listfilenames, Function=None, Pool=None, **kwargs):
    '''Return a number indicating how interesting the image is using SciPy
       '''

    if Pool is None:
        TPool = pools.GetGlobalMultithreadingPool()
    else:
        TPool = Pool;

    TileToScore = dict();
    tasklist = [];
    for filename in listfilenames:
        task = TPool.add_task('Calc Feature Score: ' + os.path.basename(filename), Function, filename, **kwargs);
        task.filename = filename;
        tasklist.append(task);

    numTasks = len(tasklist);
    iTask = 0;
    for task in tasklist:
        Result = task.wait_return();
        iTask = iTask + 1
        if Result is None:
            PrettyOutput.LogErr('No return value for ' + task.name);
            continue;

        if Result[0] is None:
            PrettyOutput.LogErr('No filename for ' + task.name);
            continue;

        PrettyOutput.CurseProgress("ImageStats", iTask, numTasks)

        filename = task.filename;
        TileToScore[filename] = Result;

    return TileToScore;

def __PruneFileSciPy__(filename, MaxOverlap=0.15, **kwargs):
    '''Returns a prune score for a single file
        Args:
           MaxOverlap = 0 to 1'''

    # logger = logging.getLogger('irtools.prune');
    logger = multiprocessing.log_to_stderr()

    if MaxOverlap > 0.5:
        MaxOverlap = 0.5;

    if not os.path.exists(filename):
        logger.error(filename + ' not found when attempting prune');
        PrettyOutput.LogErr(filename + ' not found when attempting prune');
        return;

    Im = imread(filename);
    (Height, Width) = Im.shape;

    StdDevList = [];
    MeanList = [];

    MaxDim = Height;
    if Width > Height:
        MaxDim = Width;

    SampleSize = int(ceil(MaxDim / 32));

    VertOverlapPixelRange = int(MaxOverlap * float(Height));
    HorzOverlapPixelRange = int(MaxOverlap * float(Width));

    MaskTopBorder = VertOverlapPixelRange + (SampleSize - (mod(VertOverlapPixelRange, 32)));
    MaskBottomBorder = Height - VertOverlapPixelRange - (SampleSize - (mod(VertOverlapPixelRange, 32)));

    MaskLeftBorder = HorzOverlapPixelRange + (SampleSize - (mod(HorzOverlapPixelRange, 32)));
    MaskRightBorder = Width - HorzOverlapPixelRange - (SampleSize - (mod(HorzOverlapPixelRange, 32)));

    # Calculate the top
    for iHeight in range(0, MaskTopBorder - (SampleSize - 1), SampleSize):
        for iWidth in range(0, Width - 1, SampleSize):
            StdDev = std(Im[iHeight:iHeight + SampleSize, iWidth:iWidth + SampleSize]);
            StdDevList.append(StdDev);
            # Im[iHeight:iHeight+SampleSize,iWidth:iWidth+SampleSize] = 0;

    # Calculate the sides
    for iHeight in range(MaskTopBorder, MaskBottomBorder, SampleSize):
        for iWidth in range(0, MaskLeftBorder - (SampleSize - 1), SampleSize):
            StdDev = std(Im[iHeight:iHeight + SampleSize, iWidth:iWidth + SampleSize]);
            StdDevList.append(StdDev);
            # Im[iHeight:iHeight+SampleSize,iWidth:iWidth+SampleSize] = 0.25;

        for iWidth in range(MaskRightBorder, Width - SampleSize, SampleSize):
            StdDev = std(Im[iHeight:iHeight + SampleSize, iWidth:iWidth + SampleSize]);
            StdDevList.append(StdDev);
            # Im[iHeight:iHeight+SampleSize,iWidth:iWidth+SampleSize] = 0.5;

    # Calculate the bottom
    for iHeight in range(MaskBottomBorder, Height - SampleSize, SampleSize):
        for iWidth in range(0, Width - 1, SampleSize):
            StdDev = std(Im[iHeight:iHeight + SampleSize, iWidth:iWidth + SampleSize]);
            StdDevList.append(StdDev);
            # Im[iHeight:iHeight+SampleSize,iWidth:iWidth+SampleSize] = 0.75;

    del Im;
    # core.ShowGrayscale(Im);
    return (filename, sum(StdDevList));

def Histogram(filenames, Bpp=None, MinSampleCount=None, Scale=None, numBins=None):
    '''Returns a single histogram built by combining histograms of all images
       If scale is not none the images are scaled before the histogram is collected'''

    if isinstance(filenames, str):
        listfilenames = [filenames];
    else:
        listfilenames = filenames;

    numTiles = len(listfilenames);
    if numTiles == 0:
        return dict();

    if Bpp is None:
        Bpp = images.GetImageBpp(listfilenames[0]);

    (Height, Width) = images.GetImageSize(listfilenames[0]);
    TileTotalPixels = Height * Width;

    # Figure out how many pixels belong in our sample
    numPixelsInList = TileTotalPixels * numTiles;

    if MinSampleCount is None:
        MinSampleCount = sqrt(numPixelsInList) * numTiles;

    numSamples = numPixelsInList;
    if numSamples > MinSampleCount:
        numSamples = sqrt(numPixelsInList)

        if numSamples < MinSampleCount:
            numSamples = MinSampleCount;

    SamplesPerImage = numSamples / numTiles;

    assert isinstance(listfilenames, list);

    FilenameToTask = {};
    FilenameToResult = {};
    tasks = []
    local_machine_pool = pools.GetLocalMachinePool()
    for f in listfilenames:
        task = __HistogramFileImageMagick__(f, ProcPool=local_machine_pool, Bpp=Bpp, Scale=Scale)
        FilenameToTask[f] = task

    # maxVal = (1 << Bpp) - 1;

    if numBins is None:
        numBins = 256;
        if Bpp > 8:
            numBins = 1024;
    else:
        assert(isinstance(numBins, int))


    OutputMap = {};
    minVal = None;
    maxVal = None;
    for f in list(FilenameToTask.keys()):
        task = FilenameToTask[f]
        taskOutput = task.wait_return();
        lines = taskOutput.splitlines();

        OutputMap[f] = lines;

        (fminVal, fmaxVal) = im_histogram_parser.MinMaxValues(lines);
        if minVal is None:
            minVal = fminVal;
        else:
            minVal = min(minVal, fminVal);

        if maxVal is None:
            maxVal = fmaxVal;
        else:
            maxVal = max(maxVal, fmaxVal);

    threadTasks = [];
     

    for f in list(OutputMap.keys()):
        threadTask = local_machine_pool.add_task(f, im_histogram_parser.Parse, OutputMap[f], minVal=minVal, maxVal=maxVal, numBins=numBins);
        threadTasks.append(threadTask);

    HistogramComposite = nornir_shared.histogram.Histogram.Init(minVal=minVal, maxVal=maxVal, numBins=numBins)
    for t in threadTasks:
        hist = t.wait_return();
        HistogramComposite.AddHistogram(hist.Bins);
        # histogram = IMHistogramOutput.Parse(taskOutput, minVal=minVal, maxVal=maxVal, numBins=numBins)

        # FilenameToResult[f] = [histogram, None, None];


    # FilenameToResult = __InvokeFunctionOnImageList__(listfilenames, Function=__HistogramFileImageMagick__, Pool=Pools.GetGlobalThreadPool(), ProcPool = Pools.GetGlobalClusterPool(), Bpp=Bpp, Scale=Scale)#, NumSamples=SamplesPerImage);

#    maxVal = 1 << Bpp;
#    numBins = 256;
#    if Bpp > 8:
#        numBins = 1024;


    # Sum all of the result arrays together
#    for filename in listfilenames:
#        if filename in FilenameToResult:
#            Result = FilenameToResult[filename];
#            histogram = Result[0];
# #
# #            if HistogramComposite is None:
# #                HistogramComposite = numpy.zeros(histogram.shape, dtype=numpy.int0);
# #
# #            HistogramComposite = numpy.add(HistogramComposite, histogram);
#
#            HistogramComposite.AddHistogram(histogram.Bins);


    return HistogramComposite;
 

def __HistogramFileSciPy__(filename, Bpp=None, NumSamples=None, numBins=None):
    '''Return the histogram of an image'''


    Im = imread(filename);
    (Height, Width) = Im.shape;
    NumPixels = Width * Height;

    ImOneD = reshape(Im, Width * Height, 1);

    if Bpp is None:
        Bpp = images.GetImageBpp(filename);

    if NumSamples is None:
        NumSamples = Height * Width;
    elif NumSamples > Height * Width:
        NumSamples = Height * Width;

    StepSize = int(float(NumPixels) / float(NumSamples));

    if StepSize > 1:
        Samples = numpy.random.random_integers(0, NumPixels - 1, NumSamples);
        ImOneD = ImOneD[Samples];

    if numBins is None:
        numBins = 256;
        if Bpp > 8:
            numBins = 1024;
    else:
        assert(isinstance(numBins, int))

    [histogram, low_range, binsize, extrapoints] = scipy.stats.histogram(ImOneD, numbins=numBins, defaultlimits=[0, 1]);
    return [histogram, low_range, binsize];

def __HistogramFileImageMagick__(filename, ProcPool, Bpp=None, Scale=None):

    if Scale is None:
        Scale = 1;

    # We only scale down, so if it is over 1 assume it is a percentage
    if Scale > 1:
        Scale = Scale / 100.0;

    if Scale > 1:
        Scale = 1;

    CmdTemplate = "convert %(filename)s -filter point -scale %(scale)g%% -define histogram:unique-colors=true -format %%c histogram:info:- && exit"
    Cmd = CmdTemplate % {'filename' : filename, 'scale' : Scale * 100};

    task = ProcPool.add_process(os.path.basename(filename), Cmd, shell=True);

    return task;

    # NewP = subprocess.Popen(Cmd + " && exit", shell=True, stdout=subprocess.PIPE);
    # interceptor = ProcessOutputInterceptor.HistogramOutputInterceptor(NewP,maxVal=maxVal, numBins=numBins);
    # ProcessOutputInterceptor.ProcessOutputInterceptor.Intercept(interceptor);



if __name__ == '__main__':

    Histogram = Histogram('C:\\Buildscript\\IrTools\\RawTile.png');

    import cProfile;
    import pstats;

    score = Prune('C:\\Buildscript\\IrTools\\RawTile.png', 0.1)
    PrettyOutput.Log("Score: " + str(score));

    ProfilePath = 'C:\\Buildscript\\IrTools\\BuildProfile.pr';

    ProfileDir = os.path.dirname(ProfilePath);
    if not os.path.exists(ProfileDir):

        os.makedirs(ProfileDir);

    try:
        cProfile.run("__PruneFileSciPy__('C:\\Buildscript\\IrTools\\RawTile.png', 0.1)", ProfilePath);
    finally:
        if not os.path.exists(ProfilePath):
            PrettyOutput.LogErr("No profile file found" + ProfilePath);
            sys.exit();

        pr = pstats.Stats(ProfilePath);
        if not pr is None:
            pr.sort_stats('time');
            print(str(pr.print_stats(.05)));






