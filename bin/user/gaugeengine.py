#
# Copyright (c) 2013-2014  Nick Dajda <nick.dajda@gmail.com>
#
# Distributed under the terms of the GNU GENERAL PUBLIC LICENSE
#
"""Nick's custom generator for creating visual gauge image files from weewx.

Tested on weewx release 2.5.1
Tested with sqlite, may not work with other databases.

Directions for use:

1) Put this file in the weewx/bin/user directory.
2) Add user.gaugeengine.GaugeGenerator to the list of Generators in skin.conf.
3) Add a [GaugeGenerator] section to skin.conf.
   Any gauges contained in this section are created when the report generator
   runs.
4) Guage names must match the Weewx field name, e.g. outTemp or barometer
5) Here is an example [GaugeGenerator] section:

###############################################################################
#
# Settings for Nick's gauge generator
#
[GaugeGenerator]
    image_width = 180
    image_height = 180
    labelfontsize = 12

    # This overwrites HTML_ROOT in weewx.conf if you want the images elsewhere
    HTML_ROOT = public_html/gauges/

    font_path = /usr/share/fonts/truetype/freefont/FreeSans.ttf

    # Colors...
    #
    # Format is 0xBBGGRR, so a pinky-purple color (r=FF, g=00, B=99) which would have
    # an HTML tag of #FF0099 is expressed as 0x9900FF
    fill_color = 0x4242b4
    background_color = 0xffffff
    label_color = 0x000000
    dial_color = 0x707070
    needle_outline_color = 0xb48242
    needle_fill_color = 0xb48242   # Leave option out for a transparent needle
    text_color = 0xb48242

    # How far the gauge extends, e.g. 180 is half a full dial, 270 is three quarters
    # This is ignored when plotting wind direction which always uses 360.
    # Must be an integer
    dial_arc = 270

    digitfontsize = 15
    labelfontsize = 16

    [[outTemp]]
        minvalue = -20
        maxvalue = 40
        majorstep = 10
        minorstep = 2
        digitformat = %d
        history = 24
        bins = 90

    [[barometer]]
        minvalue = 970
        maxvalue = 1050
        majorstep = 20
        minorstep = 5
        digitformat = %d
        history = 24
        bins = 80

    [[outHumidity]]
        minvalue = 0
        maxvalue = 100
        majorstep = 20
        minorstep = 5
        history = 24
        bins = 50

    [[windSpeed]]
        minvalue = 0
        maxvalue = 40
        majorstep = 10
        minorstep = 2
        history = 24
        bins = 40

    [[windGust]]
        minvalue = 0
        maxvalue = 40
        majorstep = 10
        minorstep = 2
        history = 24
        bins = 40

    [[windDir]]
        majorstep = 90
        minorstep = 30
        invert = false
        history = 24
        bins = 16
"""

import time
import syslog
import os.path

import Image

import weeutil.weeutil
import weewx.archive
import weewx.reportengine
import weeplot.utilities
import user.gauges

from weewx.units import ValueTupleDict, Converter

class GaugeGenerator(weewx.reportengine.CachedReportGenerator):
    """Class for managing the gauge generator."""

    def run(self):
        self.setup()

        # Generate any images
        self.gen_gauges()

    def setup(self):
        self.gauge_dict = self.skin_dict['GaugeGenerator']
        self.units_dict = self.skin_dict['Units']

        # Lookup the last reading in the archive
        self.archivedb = self._getArchive(self.skin_dict['archive_database'])
        rec = self._get_record(self.archivedb, self.archivedb.lastGoodStamp())
        self.record_dict_vtd = weewx.units.ValueTupleDict(rec)

    def gen_gauges(self):
        """Generate the gauges."""
        t1 = time.time()
        ngen = 0

        # Loop over each time span class (day, week, month, etc.):
        for gauge in self.gauge_dict.sections:
            plot_options = weeutil.weeutil.accumulateLeaves(self.gauge_dict[gauge])

            image_root = os.path.join(self.config_dict['WEEWX_ROOT'], plot_options['HTML_ROOT'])
            # Get the path of the file that the image is going to be saved to:
            img_file = os.path.join(image_root, '%sGauge.png' % gauge)

            # Create the subdirectory that the image is to be put in.
            # Wrap in a try block in case it already exists.
            try:
                os.makedirs(os.path.dirname(img_file))
            except:
                pass

            self.gen_gauge(gauge, plot_options, img_file)
            ngen += 1

        t2 = time.time()

        syslog.syslog(syslog.LOG_INFO, "GaugeGenerator: Generated %d images for %s in %.2f seconds" %
                                       (ngen, self.skin_dict['REPORT_NAME'], t2 - t1))

    def gen_gauge(self, gaugename, plot_options, img_file):
        image_width = int(plot_options.get('image_width', 180))
        image_height = int(plot_options.get('image_height', 180))

        back_color = weeplot.utilities.tobgr(plot_options.get('background_color', '0xffffff'))
        back_color_tuple = self._int2rgb(back_color)

        compass_labels = int(plot_options.get('compass_labels', 0))
        label_color = weeplot.utilities.tobgr(plot_options.get('label_color', '0x000000'))
        dial_color = weeplot.utilities.tobgr(plot_options.get('dial_color', '0x707070'))
        needle_outline_color = weeplot.utilities.tobgr(plot_options.get('needle_outline_color', '0xb48242'))
        needle_fill_color = plot_options.get('needle_fill_color', None)
        if needle_fill_color == None or needle_fill_color == 'None' or needle_fill_color == 'Opaque':
            needle_fill_color = None
        else:
            needle_fill_color = weeplot.utilities.tobgr(needle_fill_color)

        text_color = weeplot.utilities.tobgr(plot_options.get('text_color', '0xb48242'))
        history_color = weeplot.utilities.tobgr(plot_options.get('history_color', '0x4242b4'))

        font_path = plot_options.get('font_path', '/usr/share/fonts/truetype/freefont/FreeSans.ttf')

        label_font_size = int(plot_options.get('labelfontsize', 15))
        digit_font_size = int(plot_options.get('digitfontsize', 15))

        major_step = float(plot_options.get('majorstep'))
        try:
            minor_step = float(plot_options.get('minorstep'))
        except:
            minor_step = None

        image = Image.new("RGB", (image_width, image_height), back_color_tuple)

        # Create a new gauge instance using the gauges.py library
        if gaugename == 'windRose':
            digitformat = None
            gauge = user.gauges.WindRoseGaugeDraw(image, background_color=back_color)
        else:
            if gaugename == 'windDir':
                # Need to do some special setup for wind gauges
                min_value = 0
                max_value = 360
                dial_arc = 360
                offset_angle = 180
            else:
                min_value = float(plot_options.get('minvalue')) # Field is mandatory
                max_value = float(plot_options.get('maxvalue')) # Field is mandatory
                dial_arc = int(plot_options.get('dial_arc', 270))
                offset_angle = int(plot_options.get('offset_angle', 0))

            gauge = user.gauges.GaugeDraw(image, min_value, max_value, dial_range=dial_arc, offset_angle=offset_angle)

        # windRose is a special case of gaugename since windRose is not the name of the archive column that
        # contains the data.
        columnname = gaugename if gaugename != 'windRose' else 'windDir'

        # Do we have a reading for it?
        try:
            unit_type = self.units_dict['Groups'][self.record_dict_vtd[columnname][2]]
        except:
            syslog.syslog(syslog.LOG_INFO, "GaugeGenerator: Could not find reading for gauge '%s'" % gaugename)
            return

        # Convert it to units in skin.conf file
        value_tuple = weewx.units.convert(self.record_dict_vtd[columnname], unit_type)

        syslog.syslog(syslog.LOG_DEBUG, "GaugeGenerator: %s reading %s = %s" % (gaugename, columnname, value_tuple[0]))

        # Do we have a proper numeric reading?
        try:
            needle_value = float(value_tuple[0])
        except:
            # Log the error, do not draw the needle and display '-'
            syslog.syslog(syslog.LOG_INFO, "GaugeGenerator: %s, could not plot reading value of = %s" %
                                           (gaugename, value_tuple[0]))
            label_text = ''
            digit_format = None
        else:
            gauge.add_needle(needle_value, needle_outline_color=needle_outline_color,
                             needle_fill_color=needle_fill_color)

            label_format = self.units_dict['StringFormats'][value_tuple[1]]
            digit_format = plot_options.get("digitformat", label_format)

            label_text = unicode(label_format % value_tuple[0], "utf8")
            label_text += unicode(self.units_dict['Labels'][value_tuple[1]], "utf8")

        gauge.add_text(label_text, text_font_size=label_font_size, text_font=font_path, text_color=text_color)

        aggregate_interval = int(plot_options.get('aggregate_interval', 0))
        aggregate_type = plot_options.get('aggregate_type', None)
        if aggregate_type == 'None': aggregate_type = None

        try:
            history = int(plot_options.get('history'))
        except:
            history = None
        else:
            (data_time, data_value) = self.archivedb.getSqlVectors(columnname, self.archivedb.lastGoodStamp() -
                                                          history * 60 * 60, self.archivedb.lastGoodStamp(), aggregate_interval, aggregate_type)

            num_buckets = int(plot_options.get('bins', 10))
            history_list = []

            windspeed_history_list = None
            if gaugename == 'windRose':
                (speed_time, speed_value) = self.archivedb.getSqlVectors('windSpeed', self.archivedb.lastGoodStamp() -
                                                          history * 60 * 60, self.archivedb.lastGoodStamp(), aggregate_interval, aggregate_type)
                windspeed_history_list = []

            for i in range(len(data_value[0])):
                value_tuple = weewx.units.convert((data_value[0][i], data_value[1], data_value[2]), unit_type)
                try:
                    hist_value = float(value_tuple[0])
                except:
                    syslog.syslog(syslog.LOG_DEBUG, "GaugeGenerator: Cannot decode reading of '%s' for gauge '%s'"
                                 % (value_tuple[0], gaugename))
                else:
                    history_list.append(hist_value)
                    if gaugename == 'windRose':
                        speed_tuple = weewx.units.convert((speed_value[0][i], speed_value[1], speed_value[2]), 'knot')
                        try:
                            value_knot = float(speed_tuple[0])
                        except:
                            value_knot = 0.0
                        else:
                            windspeed_history_list.append(value_knot);

            if gaugename == 'windRose':
                rings = []
                for ring in plot_options.get('rings', [1,3,10]):
                    rings.append(int(ring))

                ring_colors = []
                for ring_color in plot_options.get('ring_colors', [0x4242b4,0xb482420,0xff0000]):
                    ring_colors.append(weeplot.utilities.tobgr(ring_color))

                gauge.add_history(history_list, num_buckets, windspeed_history_list, rings, ring_colors)
            else:
                gauge.add_history(history_list, num_buckets, history_color)

        gauge.add_dial(major_ticks=major_step, minor_ticks=minor_step, dial_format=digit_format, dial_font_size=digit_font_size,
                       dial_font=font_path, dial_color=dial_color, dial_label_color=label_color)

        if compass_labels:
            # Lookup the labels for the main compass points and add them to the gauge
            try:
                labels_dict = self.skin_dict['Labels']
            except:
                hemispheres = ['N', 'S', 'E', 'W']
            else:
                hemispheres = labels_dict.get("hemispheres", ['N', 'S', 'E', 'W'])

            compass_points = [0, 180, 90, 270]
            dial_labels = dict(zip(compass_points, hemispheres))

            gauge.add_dial_labels(dial_labels = dial_labels, dial_label_font_size=digit_font_size,
                                  dial_label_color=label_color, dial_label_font=font_path)

        gauge.render()
        image.save(img_file)

    @staticmethod
    def _get_record(archivedb, time_ts):
        """Return a value tuple dictionary which can be used to get current
        readings in skin units."""
        record_dict = archivedb.getRecord(time_ts)

        return ValueTupleDict(record_dict)

    @staticmethod
    def _int2rgb(x):
    #
    # Stolen from genploy.py Weewx file
    #
        if x is None:
            return None
        else:
            b = (x >> 16) & 0xff
            g = (x >> 8) & 0xff
            r = x & 0xff
            return r, g, b
