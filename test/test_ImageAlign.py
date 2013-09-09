'''
Created on Mar 25, 2013

@author: u0490822
'''
import unittest
import os
from pylab import *
import nornir_imageregistration.core as core
import logging
import setup_imagetest
import nornir_imageregistration.stos_brute as stos_brute


class Test(setup_imagetest.ImageTestBase):

    def setUp(self):
        super(Test, self).setUp()

        self.FixedImagePath = os.path.join(self.TestDataSource, "Fixed.png")
        self.assertTrue(os.path.exists(self.FixedImagePath), "Missing test input " + self.FixedImagePath)

        self.FixedImage = imread(self.FixedImagePath)
        self.assertIsNotNone(self.FixedImage)

        self.PaddedFixedImage = core.PadImageForPhaseCorrelation(self.FixedImage)
        self.assertIsNotNone(self.PaddedFixedImage)


    def testPhaseCorrelationToSelf(self):
        '''Align an image to itself and make sure the result is a zero offset'''
        WarpedImagePath = self.FixedImagePath

        WarpedImage = imread(WarpedImagePath)
        self.assertIsNotNone(WarpedImage)

        PaddedWarpedImage = core.PadImageForPhaseCorrelation(WarpedImage)
        self.assertIsNotNone(PaddedWarpedImage)

        record = core.FindOffset(self.PaddedFixedImage, PaddedWarpedImage)
        self.assertIsNotNone(record)

        self.assertEqual(record.angle, 0.0)
        self.assertAlmostEqual(record.peak[0], 0, msg="Expected X offset is zero when aligning image to self: %s" % str(record), delta=1)
        self.assertAlmostEqual(record.peak[1], 0, msg="Expected Y offset is zero when aligning image to self: %s" % str(record), delta=1)

    def testPhaseCorrelationToOffsetself(self):
        '''Align an image to an identical image with fixed offset and make sure the result matches the offset'''
        WarpedImagePath = os.path.join(self.TestDataSource, "Moving.png")
        self.assertTrue(os.path.exists(WarpedImagePath), "Missing test input")

        WarpedImage = imread(WarpedImagePath)
        self.assertIsNotNone(WarpedImage)

        PaddedWarpedImage = core.PadImageForPhaseCorrelation(WarpedImage)
        self.assertIsNotNone(PaddedWarpedImage)

        record = core.FindOffset(self.PaddedFixedImage, PaddedWarpedImage)
        self.assertIsNotNone(record)

        self.assertEqual(record.angle, 0.0)
        self.assertAlmostEqual(record.peak[0], 88.5, msg="Expected X offset is zero when aligning image to self: %s" % str(record), delta=1.0)
        self.assertAlmostEqual(record.peak[1], 107, msg="Expected Y offset is zero when aligning image to self: %s" % str(record), delta=1.0)

        # Try again with overlap limits that should prevent or allow a match

#        record = core.FindOffset(self.PaddedFixedImage, PaddedWarpedImage, minOv)
#        self.assertIsNotNone(record)
#
#        self.assertEqual(record.angle, 0.0)
#        self.assertAlmostEqual(record.peak[0], 107, msg = "Expected X offset is zero when aligning image to self: %s" % str(record), delta = 1.0)
#        self.assertAlmostEqual(record.peak[1], 177, msg = "Expected Y offset is zero when aligning image to self: %s" % str(record), delta = 1.0)

class TestBrandeis(setup_imagetest.ImageTestBase):
    '''Test TEM images captured on a different scope than the Moran Eye Center JEOL'''

    def testPhaseCorrelationToOffset(self):
        FixedImagePath = os.path.join(self.TestDataSource, "B030.png")
        self.assertTrue(os.path.exists(FixedImagePath), "Missing test input")

        WarpedImagePath = os.path.join(self.TestDataSource, "B029.png")
        self.assertTrue(os.path.exists(WarpedImagePath), "Missing test input")

        FixedImage = imread(FixedImagePath)
        self.assertIsNotNone(FixedImage)

        PaddedFixedImage = core.PadImageForPhaseCorrelation(FixedImage)
        self.assertIsNotNone(PaddedFixedImage)

        WarpedImage = imread(WarpedImagePath)
        self.assertIsNotNone(WarpedImage)

        PaddedWarpedImage = core.PadImageForPhaseCorrelation(WarpedImage)
        self.assertIsNotNone(PaddedWarpedImage)

        record = core.FindOffset(PaddedFixedImage, PaddedWarpedImage)
        self.assertIsNotNone(record)

        self.assertIsNotNone(record)

        self.assertEqual(record.angle, 0.0)
        self.assertAlmostEqual(record.peak[0], 452, msg="Expected X offset is zero when aligning image to self: %s" % str(record), delta=1.5)
        self.assertAlmostEqual(record.peak[1], -10, msg="Expected Y offset is zero when aligning image to self: %s" % str(record), delta=1.5)

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()