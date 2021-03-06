#!/usr/bin/env python
#coding=utf-8
from __future__ import unicode_literals
from __future__ import print_function
# from modules.classes import ExperimentalDrop, DropData, Tolerances
# from modules.static_setup_class import ExperimentalSetup
# # from modules.ui import initialise_ui
# from modules.user_interface import call_user_input
# # from modules.load import load_data
# from modules.extract_data import extract_drop_profile
# from modules.initialise_parameters import initialise_parameters
# # from modules.fit_data import fit_raw_experiment
# # from modules.user_set_regions


from modules.classes import ExperimentalSetup, ExperimentalDrop, DropData, Tolerances
from modules.PlotManager import PlotManager
from modules.opendrop_user_interface import call_user_input
from modules.read_image import get_image
from modules.opendrop_select_regions import set_regions
from modules.initialise_parameters import initialise_parameters
from modules.analyse_needle import calculate_needle_diameter
from modules.syringe_pump import SyringePump

from modules.pendant_extract_profile import PendantExtractProfile
from modules.pendant_extract_data import PendantExtractData
from modules.pendant_fit_data import PendantFitData
from modules.pendant_generate_data import PendantGenerateData
from modules.pendant_fitting_plots import PendantFittingPlots

from modules.sessile_extract_profile import SessileExtractProfile
from modules.sessile_extract_data import SessileExtractData
from modules.sessile_fit_data import SessileFitData
from modules.sessile_generate_data import SessileGenerateData
from modules.sessile_fitting_plots import SessileFittingPlots
#from opendrop_user_interface import UserInterface

# from modules. import add_data_to_lists

import os
import numpy as np
import Tkinter as tk
import tkFont

import timeit
import time

np.set_printoptions(suppress=True)
np.set_printoptions(precision=3)

DELTA_TOL = 1.e-6
GRADIENT_TOL = 1.e-6
MAXIMUM_FITTING_STEPS = 10
OBJECTIVE_TOL = 1.e-4
ARCLENGTH_TOL = 1.e-6
MAXIMUM_ARCLENGTH_STEPS = 10
NEEDLE_TOL = 1.e-4
NEEDLE_STEPS = 20


def opendrop(drop_type, auto_test):

    #clear_screen()

    fitted_drop_data = DropData()

    tolerances = Tolerances(
        DELTA_TOL,
        GRADIENT_TOL,
        MAXIMUM_FITTING_STEPS,
        OBJECTIVE_TOL,
        ARCLENGTH_TOL,
        MAXIMUM_ARCLENGTH_STEPS,
        NEEDLE_TOL,
        NEEDLE_STEPS)

    user_inputs = ExperimentalSetup()
    user_inputs.drop_type = drop_type

    if auto_test != None:

        user_inputs.auto_test_parameters = auto_test

    call_user_input(user_inputs)

    n_frames = user_inputs.number_of_frames

    if drop_type == 1:
        extract_profile = PendantExtractProfile()
        extract_data = PendantExtractData(n_frames, fitted_drop_data.parameter_dimensions)
        fit_data = PendantFitData()
        generate_data = PendantGenerateData()
    if drop_type == 2 :
        extract_profile = SessileExtractProfile()
        extract_data = SessileExtractData(n_frames, fitted_drop_data.parameter_dimensions)
        fit_data = SessileFitData()
        generate_data = SessileGenerateData()

    raw_experiment = ExperimentalDrop()

    if user_inputs.interfacial_tension_boole:
        plots = PlotManager(user_inputs.wait_time, n_frames)

    initial_volume = 0;
    current_volume = 0;
    syringe_inner_diameter = 0;
    volume_change_threshold = 0;
    abs_total_volume_change = 0;
    pump = None

    if (n_frames > 1) and (user_inputs.constant_volume_bool):
        syringe_inner_diameter = user_inputs.syringe_inner_diameter
        volume_change_threshold = user_inputs.volume_change_threshold
        pump_path = user_inputs.serial_device_path
        pump = SyringePump(pump_path)

        # Diameter is in mm
        pump.setDiameter(syringe_inner_diameter)
        # Accumulator units are dependent on the diameter value given, so we'll
        # force it to be uL
        pump.setAccumUnits("UL")
        pump.clearVolumeAccum("both")

    get_image(raw_experiment, user_inputs, -1)

    set_regions(raw_experiment, user_inputs)

    for i in range(n_frames):
        print("\nProcessing frame %d of %d..." % (i+1, n_frames))
        time_start = timeit.default_timer()
        #raw_experiment = ExperimentalDrop()
        get_image(raw_experiment, user_inputs, i) # save image in here...
        # extract_drop_profile(raw_experiment, user_inputs)

        extract_profile.extract_drop_profile(raw_experiment, user_inputs)

        if i == 0:
            extract_data.initial_image_time = raw_experiment.time
            filename = user_inputs.filename[:-4] + '_' + user_inputs.time_string + ".csv"
            export_filename = os.path.join(user_inputs.directory_string, filename)
        initialise_parameters(raw_experiment, fitted_drop_data)
        calculate_needle_diameter(raw_experiment, fitted_drop_data, tolerances)
        # fit_experimental_drop(raw_experiment, fitted_drop_data, tolerances)

        fit_data.fit_experimental_drop(raw_experiment, fitted_drop_data, user_inputs, tolerances)
        generate_data.generate_full_data(extract_data, raw_experiment, fitted_drop_data, user_inputs, i)
        data_vector = extract_data.time_IFT_vol_area(i)

        if user_inputs.interfacial_tension_boole:
            plots.append_data_plot(data_vector, i)

        if user_inputs.constant_volume_bool:
            # The 3rd element of data_vector is the drop volume in uL
            volume = data_vector[2]
            if (i != 0):
                print("Initial volume was {0:01.6f} uL.".format(initial_volume))

            print("Drop volume for frame {0} is {1:01.6f} uL.".format(i+1, volume))

            if i == 0:
                initial_volume = volume
                current_volume = volume
            else:
                current_volume = volume

            volume_difference = current_volume - initial_volume
            abs_total_volume_change += abs(volume_difference)

            if (abs(volume_difference) > volume_change_threshold) and (i != (n_frames - 1)):
                print("Difference between current drop volume and initial is {0} uL.".format(volume_difference))

                # If the volume has increased above the initial volume
                if volume_difference > 0:
                    pump_direction = "withdraw"

                # If the volume has decreased below the initial volume
                elif volume_difference < 0:
                    pump_direction = "infuse"

                # We don't care about the sign anymore, so let's avoid further calls to abs
                volume_difference = abs(volume_difference)

                # Since volume adjustments are going to be pretty small, we can
                # perform them in a few seconds without going over the max flow
                # rate of the pump
                # Currently the rate is calculated so that the adjustment is
                # completed in a fifth of the wait time between frames
                adjustment_time = int(user_inputs.wait_time) * 0.2
                rate = 60 * (volume_difference / (adjustment_time))
                print("Rate to {0} {1} uL in {2} seconds is {3} uL/min.".format(pump_direction,
                    volume_difference, adjustment_time, rate))
                # Rate is in micro litres per minute
                units = "UM"

                # This makes the pump automatically stop after the desired
                # volume has been dispensed
                pump.setVolumeToDispense(volume_difference)
                pump.setDirection(pump_direction)
                pump.setRate(rate, units)

                pump.run()

                print("Absolute total volume difference: {0}".format(abs_total_volume_change))
                print("Pumping...")
                print("Volume accumulator in nL (infuse, withdraw): {0}".format(pump.getVolumeAccum()))

        if i != (n_frames - 1):
            time_loop = timeit.default_timer() - time_start
            pause_wait_time(time_loop, user_inputs.wait_time)

        # for auto test funtion
        if auto_test != None and drop_type == 1:

            plots.fig.savefig(os.path.dirname(__file__)+'/outputs/pendantDrop_figures.jpg')

            img1 = open(os.path.dirname(__file__)+'/standard_outputs/pendantDrop_figures.jpg', "r")
            img2 = open(os.path.dirname(__file__)+'/outputs/pendantDrop_figures.jpg', "r")

            if img1.read() == img2.read():
                print("the figures output is correct")
            else:
                print("the figures output is incorrect")

        if auto_test != None and drop_type == 2:

            plots.fig.savefig(os.path.dirname(__file__) + '/outputs/sessileDrop_figures.jpg')
            img1 = open(os.path.dirname(__file__) + '/standard_outputs/sessileDrop_figures.jpg', "r")
            img2 = open(os.path.dirname(__file__) + '/outputs/sessileDrop_figures.jpg', "r")

            if img1.read() == img2.read():
                print("the figures output is correct")
            else:
                print("the figures output is incorrect")

        # end of the auto test function

        extract_data.export_data(export_filename,i)

    #cheeky_pause()
    if(auto_test != None):
        os._exit(0)
    root = tk.Tk()
    # quit button
    buttonFont = tkFont.Font(family='Helvetica', size=48, weight='bold') #This isn't working for some reason (??)
    quit_button = tk.Button(master=root, font=buttonFont, text='Quit', height=4, width=15,
                            command=lambda: quit_(root), bg='blue', fg='white', activeforeground='white',
                            activebackground='red')
    quit_button.pack()

    root.mainloop()

def clear_screen():

    os.system('cls' if os.name == 'nt' else 'clear')

def pause_wait_time(elapsed_time, requested_time):
    if elapsed_time > requested_time:
        print('WARNING: Fitting took longer than desired wait time')
    else:
        time.sleep(requested_time - elapsed_time)

def cheeky_pause():
    import Tkinter
    import tkMessageBox
    import cv2
    #    cv2.namedWindow("Pause")
    #    while 1:
    #        k = cv2.waitKey(1) & 0xFF
    #        if (k==27):
    #            break
    #root = Tkinter.Tk()
    #    B = Tkinter.Button(top, text="Exit",command = cv2.destroyAllWindows())
    #    B = Tkinter.Button(root, text="Exit",command = root.destroy())
    #
    #    B.pack()
    #    root.mainloop()

    root = Tkinter.Tk()
    frame = Tkinter.Frame(root)
    frame.pack()

    button = Tkinter.Button(frame)
    button['text'] ="Good-bye."
    button['command'] = root.destroy()#close_window(root)
    button.pack()

    root.mainloop()

def quit_(root):
    root.quit()

#def close_window(root):
#    root.destroy()
