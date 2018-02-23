'''
'''


import os

import nornir_imageregistration
import nornir_imageregistration.files.stosfile
from scipy import pi

import numpy as np


class AlignmentRecord:
    '''
    Records basic registration information as an angle and offset between a fixed and moving image
    If the offset is zero the center of both images occupy the same point.  
    The offset determines the translation of the moving image over the fixed image.
    There is no support for scale, and there should not be unless added as another variable to the alignment record
    
    :param array peak: Translation vector for moving image
    :param float weight: The strength of the alignment
    :param float angle: Angle to rotate moving image in degrees
    
    '''

    @property
    def angle(self):
        '''Rotation in degrees'''
        return self._angle

    @property
    def rangle(self):
        '''Rotation in radians'''
        return self._angle * (pi / 180.0)

    @property
    def weight(self):
        '''Quantifies the quality of the alignment'''
        return self._weight
    
    @weight.setter
    def weight(self, value):
        self._weight = value

    @property
    def peak(self):
        '''Translation vector for the alignment'''
        return self._peak

    def WeightKey(self):
        return self._weight

    def scale(self, value):
        '''Scales the peak position'''
        self._peak = self._peak * value

    def translate(self, value):
        '''Translates the peak position using tuple (Y,X)'''
        self._peak = self._peak + value

    def Invert(self):
        '''
        Returns a new alignment record with the coordinates of the peak reversed
        Used to change the frame of reference of the alignment from one tile to another
        '''
        return AlignmentRecord((-self.peak[0], -self.peak[1]), self.weight, self.angle)

    def __str__(self):
        s = 'angle: ' + str(self._angle) + ' offset: ' + str(self._peak) + ' weight: ' + str(self._weight)
        return s

    def __init__(self, peak, weight, angle=0.0):
        if not isinstance(angle, float):
            angle = float(angle)

        self._angle = angle

        if not isinstance(peak, np.ndarray):
            peak = np.array(peak)

        self._peak = peak
        self._weight = weight

    def CorrectPeakForOriginalImageSize(self, FixedImageShape, MovingImageShape):

        if self.peak is None:
            self.peak = (0, 0)

        return nornir_imageregistration.transforms.factory.__CorrectOffsetForMismatchedImageSizes(FixedImageShape, MovingImageShape)


    def GetTransformedCornerPoints(self, warpedImageSize):
        '''
        
        '''
        return nornir_imageregistration.transforms.factory.GetTransformedRigidCornerPoints(warpedImageSize, self.rangle, self.peak)


    def ToTransform(self, fixedImageSize, warpedImageSize=None):
        '''
        :param (Height, Width) fixedImageSize: Size of translated image in fixed space
        :param (Height, Width) warpedImageSize: Size of translated image in warped space.   If unspecified defaults to fixedImageSize
        :return: A rigid rotation+translation transform described by the alignment record
        '''

        if warpedImageSize is None:
            warpedImageSize = fixedImageSize

        return nornir_imageregistration.transforms.factory.CreateRigidTransform(fixedImageSize, warpedImageSize, self.rangle, self.peak)

    def __ToGridTransformString(self, fixedImageSize, warpedImageSize):

        transform = self.ToTransform(fixedImageSize, warpedImageSize)

        warpedSpaceCorners = nornir_imageregistration.transforms.factory.GetTransformedRigidCornerPoints(warpedImageSize, rangle=0, offset=(0, 0))

        fixedSpaceCorners = transform.Transform(warpedSpaceCorners)

#        list = [str(BotLeft.item(0)),
#                str(BotLeft.item(1)),
#                str(BotRight.item(0)),
#                str(BotRight.item(1)),
#                str(TopLeft.item(0)),
#                str(TopLeft.item(1)),
#                str(TopRight.item(0)),
#                str(TopRight.item(1))]

        string = ""

        fixedSpaceCorners = np.fliplr(fixedSpaceCorners)

        for s in fixedSpaceCorners.flat:
            string = string + ' %g' % s

        return string

    def ToStos(self, ImagePath, WarpedImagePath, FixedImageMaskPath=None, WarpedImageMaskPath=None, PixelSpacing=1):
        stos = nornir_imageregistration.files.stosfile.StosFile()
        stos.ControlImageName = os.path.basename(ImagePath)
        stos.ControlImagePath = os.path.dirname(ImagePath)

        stos.MappedImageName = os.path.basename(WarpedImagePath)
        stos.MappedImagePath = os.path.dirname(WarpedImagePath)

        if not FixedImageMaskPath is None:
            stos.ControlMaskName = os.path.basename(FixedImageMaskPath)
            stos.ControlMaskPath = os.path.dirname(FixedImageMaskPath)

        if not WarpedImageMaskPath is None:
            stos.MappedMaskName = os.path.basename(WarpedImageMaskPath)
            stos.MappedMaskPath = os.path.dirname(WarpedImageMaskPath)

        (ControlHeight, ControlWidth) = nornir_imageregistration.core.GetImageSize(ImagePath)
        stos.ControlImageDim = (ControlWidth, ControlHeight)

        (MappedHeight, MappedWidth) = nornir_imageregistration.core.GetImageSize(WarpedImagePath)
        stos.MappedImageDim = (MappedWidth, MappedHeight)

        # transformTemplate = "FixedCenterOfRotationAffineTransform_double_2_2 vp 8 %(cos)g %(negsin)g %(sin)g %(cos)g %(x)g %(y)g 1 1 fp 2 %(mapwidth)d %(mapheight)d"

        # stos.Transform = transformTemplate % {'cos' : cos(Match.angle * numpy.pi / 180),
        #                                 'sin' : sin(Match.angle * numpy.pi / 180),
        #                                 'negsin' : -sin(Match.angle * numpy.pi / 180),
        #                                 'x' : Match.peak[0],
        #                                 'y' : -Match.peak[1],
        #                                 'mapwidth' : stos.MappedImageDim[0]/2,
        #                                 'mapheight' : stos.MappedImageDim[1]/2}

        transformTemplate = "GridTransform_double_2_2 vp 8 %(coordString)s fp 7 0 1 1 0 0 %(width)f %(height)f"

        # We use Y,X ordering in memory due to Numpy.  Ir-Tools coordinates are written X,Y.
        coordString = self.__ToGridTransformString((stos.ControlImageDim[1], stos.ControlImageDim[0]), (stos.MappedImageDim[1], stos.MappedImageDim[0]))

        stos.Transform = transformTemplate % {'coordString' : coordString,
                                              'width' : stos.MappedImageDim[0] - 1,
                                              'height' : stos.MappedImageDim[1] - 1}

        stos.Downsample = PixelSpacing

#        print "Done!"

        return stos
