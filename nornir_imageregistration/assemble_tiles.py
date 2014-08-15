'''
Created on Oct 28, 2013

Deals with assembling images composed of mosaics or dividing images into tiles
'''

import numpy as np
from scipy import stats
import scipy.spatial.distance
import os
import logging

import nornir_imageregistration.assemble  as assemble
# from nornir_imageregistration.files.mosaicfile import MosaicFile
# from nornir_imageregistration.mosaic import Mosaic
import nornir_imageregistration.core as core
import nornir_imageregistration.transforms.utils as tutils
import nornir_imageregistration.tileset as tiles
# import nornir_imageregistration.transforms.meshwithrbffallback as meshwithrbffallback
# import nornir_imageregistration.transforms.triangulation as triangulation
import nornir_pools as pools
import copy
import tempfile

import nornir_imageregistration.spatial as spatial

DistanceImageCache={}

class TransformedImageData(object):

    @property
    def image(self):
        return self._image

    @property
    def centerDistanceImage(self):
        return self._centerDistanceImage

    @property
    def transformScale(self):
        return self._transformScale

    @property
    def transform(self):
        return self._transform

    @property
    def errormsg(self):
        return self._errmsg

    @classmethod
    def Create(cls, image, centerDistanceImage, transform, scale):
        o = TransformedImageData()
        o._image = image
        o._centerDistanceImage = centerDistanceImage
        o._transformScale = scale
        o._transform = transform

        return o


    def Clear(self):
        '''Sets attributes to None to encourage garbase collection'''
        self._image = None
        self._centerDistanceImage = None
        self._transformScale = None
        self._transform = None


    def __init__(self, errorMsg=None):
        self._image = None
        self._centerDistanceImage = None
        self._transformScale = None
        self._transform = None
        self._errmsg = errorMsg

def CompositeImage(FullImage, SubImage, offset):

    minX = offset[1]
    minY = offset[0]
    maxX = minX + SubImage.shape[1]
    maxY = minY + SubImage.shape[0]

    iNonZero = SubImage > 0.0

    temp = FullImage[minY:maxY, minX:maxX]

    temp[iNonZero] = SubImage[iNonZero]

    # FullImage[minY:maxY, minX:maxX] += SubImage
    FullImage[minY:maxY, minX:maxX] = temp

    return FullImage


def CompositeImageWithZBuffer(FullImage, FullZBuffer, SubImage, SubZBuffer, offset):

    minX = int(offset[1])
    minY = int(offset[0])
    maxX = int(minX + SubImage.shape[1])
    maxY = int(minY + SubImage.shape[0])

    tempFullImage = FullImage[minY:maxY, minX:maxX]
    tempZBuffer = FullZBuffer[minY:maxY, minX:maxX]

    if(tempZBuffer.shape != SubZBuffer.shape):
        raise ValueError("Buffers do not have the same dimensions")

    iUpdate = tempZBuffer > SubZBuffer

    tempFullImage[iUpdate] = SubImage[iUpdate]
    tempZBuffer[iUpdate] = SubZBuffer[iUpdate]

    # FullImage[minY:maxY, minX:maxX] += SubImage
    FullImage[minY:maxY, minX:maxX] = tempFullImage
    FullZBuffer[minY:maxY, minX:maxX] = tempZBuffer

    return (FullImage, FullZBuffer)


def distFunc(i, j):
    print((str(i) + ", " + str(j)))
    a = np.array(i, dtype=np.float)
    a = a * a
    b = np.array(j, dtype=np.float)
    b = b * b
    c = a + b
    c = np.sqrt(c)
    return c
    # return scipy.spatial.distance.cdist(np.dstack((i, j)), np.array([[5.0], [5.0]], dtype=np.float))


    
def CreateDistanceImage(shape, dtype=None):

    if dtype is None:
        dtype = np.float32

    center = [shape[0] / 2.0, shape[1] / 2.0]

    x_range = np.linspace(-center[1], center[1], shape[1])
    y_range = np.linspace(-center[0], center[0], shape[0])

    x_range = x_range * x_range
    y_range = y_range * y_range

    distance = np.empty(shape, dtype=dtype)

    for i in range(0, shape[0]):
        distance[i, :] = x_range + y_range[i]

    distance = np.sqrt(distance)

    return distance


def __MaxZBufferValue(dtype):
    return np.finfo(dtype).max


def EmptyDistanceBuffer(shape, dtype=np.float16):
    fullImageZbuffer = np.empty(shape, dtype=dtype)
    fullImageZbuffer.fill(__MaxZBufferValue(dtype))
    return fullImageZbuffer

def __CreateOutputBufferForTransforms(transforms, requiredScale=None):
    '''Create output images using the passed rectangle
    :param tuple rectangle: (minY, minX, maxY, maxX)
    :return: (fullImage, ZBuffer)
    '''
    (minY, minX, maxY, maxX) = tutils.FixedBoundingBox(transforms)

    fullImage = np.zeros((np.ceil(requiredScale * maxY), np.ceil(requiredScale * maxX)), dtype=np.float16)
    fullImageZbuffer = EmptyDistanceBuffer(fullImage.shape, dtype=fullImage.dtype)
    return (fullImage, fullImageZbuffer)


def __CreateOutputBufferForArea(Height, Width, requiredScale=None):
    '''Create output images using the passed width and height
    '''

    fullImage = np.zeros((int(np.ceil(requiredScale * Height)), int(np.ceil(requiredScale * Width))), dtype=np.float16)
    fullImageZbuffer = EmptyDistanceBuffer(fullImage.shape, dtype=fullImage.dtype) 
    return (fullImage, fullImageZbuffer)


def __GetOrCreateCachedDistanceImage(imageShape):
    distance_array_path = os.path.join(tempfile.gettempdir(), 'distance%dx%d.npy' % (imageShape[0],imageShape[1]))
    
    distanceImage = None
    if os.path.exists(distance_array_path):
        #distanceImage = core.LoadImage(distance_image_path)
        try:
            distanceImage = np.load(distance_array_path)
        except:
            print("Unable to load distance_image %s" % (distance_array_path))
            try:
                os.remove(distance_array_path)
            except:
                print("Unable to delete invalid distance_image: %s" % (distance_array_path))
                pass
            
            pass
    
    if distanceImage is None:
        distanceImage = CreateDistanceImage(imageShape)
        try:
            np.save(distance_array_path, distanceImage)
        except:
            print("Unable to save invalid distance_image: %s" % (distance_array_path))
            pass
        
    return distanceImage
     

def __GetOrCreateDistanceImage(distanceImage, imageShape):
    '''Determines size of the image.  Returns a distance image to match the size if the passed existing image is not the correct size.'''

    assert(len(imageShape)==2)
    size = imageShape
    if not distanceImage is None:
        if np.array_equal(distanceImage.shape, size):
            return distanceImage
                
    return __GetOrCreateCachedDistanceImage(imageShape)


def TilesToImage(transforms, imagepaths, FixedRegion=None, requiredScale=None):
    '''

    :param tuple FixedRegion: (MinX, MinY, Width, Height)

    '''

    assert(len(transforms) == len(imagepaths))

    logger = logging.getLogger(__name__ + '.TilesToImage')

    if requiredScale is None:
        requiredScale = tiles.MostCommonScalar(transforms, imagepaths)

    distanceImage = None
    fixedRect = None
    fullImage = None
    fullImageZBuffer = None

    if not FixedRegion is None:
        fixedRect = spatial.Rectangle.CreateFromPointAndArea((FixedRegion[0], FixedRegion[1]), (FixedRegion[2] - FixedRegion[0], FixedRegion[3] - FixedRegion[1]))
        (fullImage, fullImageZbuffer) = __CreateOutputBufferForArea(FixedRegion[2] - FixedRegion[0], FixedRegion[3] - FixedRegion[1], requiredScale)
    else:
        (fullImage, fullImageZbuffer) = __CreateOutputBufferForTransforms(transforms, requiredScale)

    minY = 0
    minX = 0
        
    for i, transform in enumerate(transforms):

        if not fixedRect is None:
            trect = spatial.Rectangle(transform.FixedBoundingBox)
            # assert(False)  # Friday, left off here.  Rectangle creation isn't correct.
            if not spatial.Rectangle.contains(trect, fixedRect):
                continue

        imagefullpath = imagepaths[i]
        
        distanceImage = __GetOrCreateDistanceImage(distanceImage, core.GetImageSize(imagefullpath))

        transformedImageData = TransformTile(transform, imagefullpath, distanceImage, requiredScale=requiredScale, FixedRegion=FixedRegion)

        if fixedRect is None:
            (minY, minX, maxY, maxX) = transformedImageData.transform.FixedBoundingBox

        (fullImage, fullImageZbuffer) = CompositeImageWithZBuffer(fullImage, fullImageZbuffer, transformedImageData.image, transformedImageData.centerDistanceImage, (np.floor(minY), np.floor(minX)))

        del transformedImageData

    mask = fullImageZbuffer < __MaxZBufferValue(fullImageZbuffer.dtype)
    del fullImageZbuffer

    fullImage[fullImage < 0] = 0
    fullImage[fullImage > 1.0] = 1.0

    return (fullImage, mask)


def TilesToImageParallel(transforms, imagepaths, FixedRegion=None, requiredScale=None, pool=None):
    '''Assembles a set of transforms and imagepaths to a single image using parallel techniques'''

    assert(len(transforms) == len(imagepaths))

    logger = logging.getLogger('TilesToImageParallel')

    distanceImage = None

    if requiredScale is None:
        requiredScale = tiles.MostCommonScalar(transforms, imagepaths)

    if pool is None:
        pool = pools.GetGlobalMultithreadingPool()

    tasks = []
    fixedRect = None
    fullImage = None
    fullImageZBuffer = None
     

    if not FixedRegion is None:
        fixedRect = spatial.Rectangle.CreateFromPointAndArea((FixedRegion[0], FixedRegion[1]), (FixedRegion[2] - FixedRegion[0], FixedRegion[3] - FixedRegion[1]))
        (fullImage, fullImageZbuffer) = __CreateOutputBufferForArea(FixedRegion[2] - FixedRegion[0], FixedRegion[3] - FixedRegion[1], requiredScale)
    else:
        (fullImage, fullImageZbuffer) = __CreateOutputBufferForTransforms(transforms, requiredScale)

    CheckTaskInterval = 10

    minY = 0
    minX = 0

    for i, transform in enumerate(transforms):

        if not fixedRect is None:
            trect = spatial.Rectangle(transform.FixedBoundingBox)
            # assert(False)  # Friday, left off here.  Rectangle creation isn't correct.
            if not spatial.Rectangle.contains(trect, fixedRect):
                continue

        imagefullpath = imagepaths[i]

        task = pool.add_task("TransformTile" + imagefullpath, TransformTile, transform=transform, imagefullpath=imagefullpath, distanceImage=None, requiredScale=requiredScale, FixedRegion=FixedRegion)
        task.transform = transform
        tasks.append(task)

        if not i % CheckTaskInterval == 0:
            continue

        for iTask, t in enumerate(tasks):
            if t.iscompleted:
                transformedImageData = t.wait_return()
                (fullImage, fullImageZbuffer) = __AddTransformedTileToComposite(transformedImageData, fullImage, fullImageZbuffer, FixedRegion)
                del transformedImageData
                del tasks[iTask]

    logger.info('All warps queued, integrating results into final image')

    while len(tasks) > 0:
        t = tasks.pop()
        transformedImageData = t.wait_return()

        if transformedImageData is None:
            logger = logging.getLogger('TilesToImageParallel')
            logger.error('Convert task failed: ' + str(t))
            continue

        (fullImage, fullImageZbuffer) = __AddTransformedTileToComposite(transformedImageData, fullImage, fullImageZbuffer, FixedRegion)
        del transformedImageData
        del t

    mask = fullImageZbuffer < __MaxZBufferValue(fullImageZbuffer.dtype)
    del fullImageZbuffer

    fullImage[fullImage < 0] = 0
    fullImage[fullImage > 1.0] = 1.0

    logger.info('Final image complete')

    return (fullImage, mask)


def __AddTransformedTileToComposite(transformedImageData, fullImage, fullImageZBuffer, FixedRegion=None):

    if transformedImageData.image is None:
        logger = logging.getLogger('TilesToImageParallel')
        logger.error('Convert task failed: ' + str(transformedImageData))
        if not transformedImageData.errormsg is None:
            logger.error(transformedImageData.errormsg)
            return (fullImage, fullImageZBuffer)

    minY = 0
    minX = 0
    if FixedRegion is None:
        (minY, minX, maxY, maxX) = transformedImageData.transform.FixedBoundingBox

    # print "%g %g" % (minX, minY)
    try:
        (fullImage, fullImageZBuffer) = CompositeImageWithZBuffer(fullImage, fullImageZBuffer, transformedImageData.image, transformedImageData.centerDistanceImage, (np.floor(minY), np.floor(minX)))
    except ValueError:
        # This is frustrating and usually indicates the input transform passed to assemble mapped to negative coordinates.
        logger = logging.getLogger('TilesToImageParallel')
        logger.error('Transformed tile mapped to negative coordinates ' + str(transformedImageData))
        pass

    transformedImageData.Clear()

    return (fullImage, fullImageZBuffer)


def TransformTile(transform, imagefullpath, distanceImage=None, requiredScale=None, FixedRegion=None):
    '''Transform the passed image.  DistanceImage is an existing image recording the distance to the center of the
       image for each pixel.  requiredScale is used when the image size does not match the image size encoded in the
       transform.  A scale will be calculated in this case and if it does not match the required scale the tile will 
       not be transformed.
       :param transform transform: Transformation used to map pixels from source image to output image
       :param str imagefullpath: Full path to the image on disk
       :param ndarray distanceImage: Optional pre-allocated array to contain the distance of each pixel from the center for use as a depth mask
       :param float requiredScale: Optional pre-calculated scalar to apply to the transform.  If None the scale is calculated based on the difference
                                   between input image size and the image size of the transform
       :param array FixedRegion: [MinY MinX MaxY MaxX] If specified only the specified region is transformed.  Otherwise transform the entire image.'''

    if not FixedRegion is None:
        spatial.RaiseValueErrorOnInvalidBounds(FixedRegion)

    if not os.path.exists(imagefullpath):
        return TransformedImageData(errorMsg='Tile does not exist ' + imagefullpath)



    # if isinstance(transform, meshwithrbffallback.MeshWithRBFFallback):
       # Don't bother mapping points falling outside the defined boundaries because we won't have image data for it
    #   transform = triangulation.Triangulation(transform.points)

    warpedImage = core.LoadImage(imagefullpath)
    if warpedImage is None:
        raise IOError("Unable to load image: %s" % (imagefullpath))

    # Automatically scale the transform if the input image shape does not match the transform bounds
    transformScale = tiles.__DetermineTransformScale(transform, warpedImage.shape)

    if not requiredScale is None:
        if not core.ApproxEqual(transformScale, requiredScale):
            return TransformedImageData(errorMsg="%g scale needed for %s is different than required scale %g used for mosaic" % (transformScale, imagefullpath, requiredScale))
        
        transformScale = requiredScale #This is needed because we aren't specifying the size of the output tile like we should be

    if transformScale != 1.0:
        scaledTransform = copy.deepcopy(transform)
        scaledTransform.Scale(transformScale)
        transform = scaledTransform

        if not FixedRegion is None:
            FixedRegion = np.array(FixedRegion) * transformScale

    (width, height, minX, minY) = (0, 0, 0, 0)

    if FixedRegion is None:

        width = transform.FixedBoundingBoxWidth
        height = transform.FixedBoundingBoxHeight

        (minY, minX, maxY, maxX) = transform.FixedBoundingBox
    else:
        assert(len(FixedRegion) == 4)
        (minY, minX, height, width) = (FixedRegion[0], FixedRegion[1], FixedRegion[2] - FixedRegion[0], FixedRegion[3] - FixedRegion[1])
        
    height = np.ceil(height)
    width = np.ceil(width)

    distanceImage = __GetOrCreateDistanceImage(distanceImage, warpedImage.shape)

    (fixedImage, centerDistanceImage) = assemble.WarpedImageToFixedSpace(transform,
                                                                         (height, width),
                                                                         [warpedImage, distanceImage],
                                                                         botleft=(minY, minX),
                                                                         area=(height, width),
                                                                         cval=[0, __MaxZBufferValue(np.float16)])

    del warpedImage
    del distanceImage

    return TransformedImageData.Create(fixedImage, centerDistanceImage, transform, transformScale)

if __name__ == '__main__':
    pass