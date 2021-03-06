# -*- coding: utf-8 -*-
#
# Copyright (c) 2011-2011, RMIT e-Research Office
#   (RMIT University, Australia)
# Copyright (c) 2010-2011, Monash e-Research Centre
#   (Monash University, Australia)
# Copyright (c) 2010-2011, VeRSI Consortium
#   (Victorian eResearch Strategic Initiative, Australia)
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    *  Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    *  Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#    *  Neither the name of the VeRSI, the VeRSI Consortium members, nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE REGENTS AND CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""
exiftags.py

.. moduleauthor:: Russell Sim <russell.sim@monash.edu>
.. moduleauthor:: Ian Thomas <Ian.Edward.Thomas@rmit.edu.au>
.. moduleauthor:: Joanna H. Huang <Joanna.Huang@versi.edu.au>

"""
import logging
import os
import random
import ConfigParser
import Image

from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

from tardis.tardis_portal.models import Schema, DatafileParameterSet
from tardis.tardis_portal.models import ParameterName, DatafileParameter
from tardis.tardis_portal.models import DatasetParameter
from tardis.microtardis.views import write_thumbnails

from fractions import Fraction


logger = logging.getLogger(__name__)
try:
    import tardis.microtardis.filters.lib.sourceforge.exif_py.EXIF as EXIF
except ImportError:
    import sys
    logger.debug("Error: Can't find the file 'EXIF.py' in the directory containing %r" % __file__)
    sys.exit(1)

class EXIFTagsFilter(object):
    """This filter provides extraction of metadata extraction of images from the RMMF
    from images.

    If a white list is specified then it takes precidence and all
    other tags will be ignored.

    :param name: the short name of the schema.
    :type name: string
    :param schema: the name of the schema to load the EXIF data into.
    :type schema: string
    :param tagsToFind: a list of the tags to include.
    :type tagsToFind: list of strings
    :param tagsToExclude: a list of the tags to exclude.
    :type tagsToExclude: list of strings
    """
    def __init__(self, name, schema, tagsToFind=[], tagsToExclude=[]):
        self.name = name
        self.schema = schema
        self.tagsToFind = tagsToFind
        self.tagsToExclude = tagsToExclude
        self.instruments = {
            'Quanta200': (('Quanta200_EXIF', 'Quanta200_EXIF', 
                           (['User', 'Usertext', 'UserText', None, None], 
                            ['User', 'Date', 'Date', None, None], 
                            ['User', 'Time', 'Time', None, None],
                            ['Beam', 'HV', 'HV', 'kV', 0.001],
                            ['Beam', 'Spot', 'Spot', None, None],
                            ['Scan', 'PixelWidth', 'PixelWidth', None, None],
                            ['Scan', 'Horfieldsize', 'HorFieldSize', None, None],
                            ['Stage', 'WorkingDistance', 'WorkingDistance', 'mm', 1000],
                            ['Vacuum', 'UserMode', 'UserMode', None, None],
                            ['Vacuum', 'CHPressure', 'CHPressure', None, None],
                            ['Detectors', 'Name', 'Name', None, None],
                            ['Detector_Name', 'Contrast', 'Contrast', None, None],
                            ['Detector_Name', 'Brightness', 'Brightness', None, None],
                            ),
                           ),
                          ),
            'NovaNanoSEM': (('NovaNanoSEM_EXIF', 'NovaNanoSEM_EXIF',
                             (['User', 'UserText', 'UserText', None, None], 
                              ['User', 'Date', 'Date', None, None], 
                              ['User', 'Time', 'Time', None, None],
                              ['Beam', 'HV', 'HV', 'kV', 0.001],
                              ['Beam', 'Spot', 'Spot', None, None],
                              ['Scan', 'PixelWidth', 'PixelWidth', None, None],
                              ['Scan', 'HorFieldsize', 'HorFieldSize', None, None],
                              ['Stage', 'WorkingDistance', 'WorkingDistance', 'mm', 1000],
                              ['Vacuum', 'UserMode', 'UserMode', None, None],
                              ['Vacuum', 'ChPressure', 'CHPressure', None, None],
                              ['Detectors', 'Name', 'Name', None, None],
                              ['Detector_Name', 'Contrast', 'Contrast', None, None],
                              ['Detector_Name', 'Brightness', 'Brightness', None, None],
                              ),
                             ),
                            ),
            'XL30': (('XL30_EXIF', 'XL30_EXIF',
                      (['DatabarData', 'flAccV', 'AccVoltage', 'kV', 0.001], 
                       ['DatabarData', 'flSpot', 'Spot', None, None], 
                       ['DatabarData', 'lDetName', 'DetectorName', None, None],
                       ['DatabarData', 'flWD', 'WorkingDistance', None, None],
                       ['DatabarData', 'lScanSpeed', 'ScanSpeed', None, None],
                       ['DatabarData', 'ImageName', 'ImageName', None, None],
                       ['Vector', 'SpecimenTilt', 'SpecimenTilt', None, None],
                       ['Vector', 'Magnification', 'Magnification', 'X', None],
                       ['Vector', 'HighTension', 'HighTension', None, None],
                       ['Vector', 'FWD', 'FreeWorkingDistance', None, None],
                       ),
                      ),
                     ),
        }
        
        logger.debug('initialising EXIFTagsFilter')

    def __call__(self, sender, **kwargs):
        """post save callback entry point.

        :param sender: The model class.
        :param instance: The actual instance being saved.
        :param created: A boolean; True if a new record was created.
        :type created: bool
        """
        instance = kwargs.get('instance')
        created = kwargs.get('created')
#        if not created:
#            # Don't extract on edit
#            return
#        #  schema = self.getSchema()
        
        filepath = instance.get_absolute_filepath()
        if not filepath:
            # TODO log that exited early
            return
        
        # generate thumbnails for image file
        try:
            img =  Image.open(filepath)
            write_thumbnails(instance, img)
        except IOError:
            # file not an image file
            pass
        
        # ignore non-image file
        if filepath[-4:].lower() != ".tif":
            return
       
        # Find instrument name in filepath
        instr_name = None 
        import re
        pathSep = re.compile(r'\\|\/')
        for part in pathSep.split(filepath):
            if part in self.instruments.keys():
                instr_name = part

        # Find instrument name in dataset metadata
        if not instr_name:
            # couldn't find it in filepath, then try dataset metadata
            dataset_params = DatasetParameter.objects.filter(parameterset__dataset__id=instance.dataset.id)
            for dataset_param in dataset_params:
                str_value = str(dataset_param.string_value)
                if str_value.startswith('http://'):
                    parts = str_value.split('/')
                    if len(parts) > 4:
                        instr_name = parts[4]
                else:
                    continue

        logger.debug("filepath=%s" % filepath)
        logger.debug("instr_name=%s" % instr_name)

        if (instr_name != None and len(instr_name) > 1):
            
            logger.debug("instr_name %s" % instr_name)
            exifs = self.getExif(filepath)
            
            for exifTag in exifs:
                logger.debug("exifTag=%s" % exifTag)
                if exifTag == 'Image Tag 0x877A' or exifTag == 'Image Tag 0x8778':
                    tmpfile = "/tmp/workfile_%s" % random.randint(1, 9999)
                    f = open(tmpfile, 'w')
                    f.write(exifs[exifTag])
                    f.close()
                    x877a_tags = ConfigParser.RawConfigParser()
                    x877a_tags.read(tmpfile)
                    
                    instrSchemas = self.instruments[instr_name]
                    # for each schema for this instrument 
                    for sch in instrSchemas:
                     
                        (schemaName,schemaSuffix,tagsToFind) = sch
                        logger.debug("schemaTuple %s  = %s %s %s" %(sch,schemaName,schemaSuffix,tagsToFind))

                        # find values in tags
                        metadata = {}
                        detector_name = ""
                        pixel_width = 0
                        for tag in tagsToFind:
                            (section, option, fieldname, unit, multiplier) = tag
                            try:
                                # get values in detector section
                                if section == "Detector_Name" and detector_name != "":
                                    section = detector_name
                                value = x877a_tags.get(section, option)
                                # convert value with specified multiplier
                                if multiplier:
                                    value = float(value) * multiplier
                                # round values
                                if option in ["WorkingDistance", "Contrast", "Brightness"]:
                                    value = round(float(value), 1)
                                if option in ["Magnification"]:
                                    value = int(round(float(value)))
                                # get Chamber Pressure
                                if section == "Vacuum" and option.lower() == "chpressure":
                                    value_in_torr = float(value) / 133.322368
                                    value_in_mbar = float(value) / 100
                                    value = "%.4G Torr (%.4G mbar)" % (value_in_torr, value_in_mbar)
                                # get metadata
                                metadata["[%s] %s" % (section, fieldname)] = [value, unit]
                                # get Detector Name
                                if section == "Detectors" and option == "Name":
                                    detector_name = value
                                # get Pixel Width for calculating magnification
                                if section == "Scan" and option == "PixelWidth":
                                    pixel_width = float(value)
                            except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
                                pass
                            
                        # Calculate Magnification
                        if pixel_width and instr_name in ["Quanta200", "NovaNanoSEM"]:
                            section = "Scan"
                            option = "Original Magnification (Full Screen)"
                            
                            if instr_name == "Quanta200":
                                monitor_pixel_width = 0.00025
                            if instr_name == "NovaNanoSEM":
                                monitor_pixel_width = 0.000291406
                            value = round( monitor_pixel_width / pixel_width )
                            unit = "X"
                            # get metadata
                            metadata["[%s] %s" % (section, option)] = [value, unit]

                        # only save exif data if we found some expected metadata
                        logger.debug("metadata = %s" % metadata)
                        if len(metadata) > 0:
                            # Make instrument specific schema                          
                            instrNamespace = ''.join([self.schema, "/" , schemaSuffix]) 

                            # create schema if needed
                            try:
                                schema =  Schema.objects.get(namespace__exact=instrNamespace)
                                logger.debug("found existing metadata schema %s" % schema)
                            except Schema.DoesNotExist:
                                schema = Schema(namespace=instrNamespace, name=schemaName,type=Schema.DATAFILE)
                                logger.debug("creating new metadata schema %s" % schema)
                                schema.save()
                            # and save metadata
                            ps = self.saveExifMetadata(instance, schema, metadata)
                            logger.debug("ps=%s" % ps)
                            
                    os.remove(tmpfile)

    def saveExifMetadata(self, instance, schema, metadata):
        """Save all the metadata to a Dataset_Files paramamter set.
        """
        parameters = self.getParamaters(schema, metadata)
        if not parameters:
            return None

        (ps, created) = DatafileParameterSet.objects.get_or_create(schema=schema, dataset_file=instance)
        if created: # new object was created
            ps.save()
        else: # if parameter set already exists then just return it
            return ps 

        for p in parameters:
            if p.name in metadata:
                dfp = DatafileParameter(parameterset=ps,
                                        name=p)
                if p.isNumeric():
                    dfp.numerical_value = metadata[p.name][0]
                else:
                    dfp.string_value = metadata[p.name][0]
                dfp.save()
        return ps

    def getParamaters(self, schema, metadata):
        """Return a list of the paramaters that will be saved.
        """
        param_objects = ParameterName.objects.filter(schema=schema)
        parameters = []
        for p in metadata:

            if self.tagsToFind and not p in self.tagsToFind:
                continue

            if p in self.tagsToExclude:
                continue

            parameter = filter(lambda x: x.name == p, param_objects)

            if parameter:
                parameters.append(parameter[0])
                continue

            # detect type of parameter
            datatype = ParameterName.STRING
             
            # integer data type test
            try:
                int(metadata[p][0])
            except (ValueError, TypeError):
                pass
            else:
                datatype = ParameterName.NUMERIC
            
            # float data type test
            try:
                float(metadata[p][0])
            except (ValueError, TypeError):
                pass
            else:
                datatype = ParameterName.NUMERIC
            
            # fraction data type test
            if isinstance(metadata[p][0], Fraction):
                datatype = ParameterName.NUMERIC

            unit = ""
            if metadata[p][1]:
                unit = metadata[p][1]
                
            new_param = ParameterName(schema=schema,
                                      name=p,
                                      full_name=p,
                                      data_type=datatype,
                                      units=unit)
            new_param.save()
            parameters.append(new_param)
        return parameters

    def getSchema(self):
        """Return the schema object that the paramaterset will use.
        """
        try:
            return Schema.objects.get(namespace__exact=self.schema)
        except Schema.DoesNotExist:
            schema = Schema(namespace=self.schema, name=self.name,
                            type=Schema.DATAFILE)
            schema.save()
            return schema




    def getExif(self, filename):
        """Return a dictionary of the metadata.
        """
        logger.debug("Extracting EXIF metadata from image...")
        ret = {}
        try:
            img = open(filename)
            exif_tags = EXIF.process_file(img)
            for tag in exif_tags:
                # EXIF.py has custom str function, use it to get correct values.
                s = str(exif_tags[tag])
                try:
                    ret[tag] = float(s)
                except ValueError:
                    ret[tag] = s
        except:
            logger.debug("Failed to extract EXIF metadata from image.")
            return ret
        
        logger.debug("Successed extracting EXIF metadata from image.")
        return ret



def make_filter(name='', schema='', tagsToFind=[], tagsToExclude=[]):
    if not name:
        raise ValueError("EXIFTagsFilter requires a name to be specified")
    if not schema:
        raise ValueError("EXIFTagsFilter required a schema to be specified") 
    return EXIFTagsFilter(name, schema, tagsToFind, tagsToExclude)

make_filter.__doc__ = EXIFTagsFilter.__doc__
